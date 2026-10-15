"""Load Ookla's quarterly open data for Greece."""

from __future__ import annotations

import argparse
import shutil
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

import duckdb
import httpx
import psycopg
from psycopg.rows import TupleRow

from db.connect import connect

SOURCE = (
    "https://ookla-open-data.s3.amazonaws.com/parquet/performance"
    "/type={kind}/year={year}/quarter={quarter}"
    "/{year}-{month:02d}-01_performance_{kind}_tiles.parquet"
)

# mainland, Crete, Dodecanese, Corfu. Generous, a tight box loses an island
WEST, SOUTH, EAST, NORTH = 19.3, 34.7, 29.7, 41.8

KINDS = ("fixed", "mobile")

READ = """
select quadkey, tile_x, tile_y, avg_d_kbps, avg_u_kbps, avg_lat_ms, tests, devices
from read_parquet(?)
where tile_x between ? and ? and tile_y between ? and ?
"""


@dataclass(frozen=True)
class Cell:
    quadkey: str
    family: str
    observed_on: date
    down_mbps: float
    up_mbps: float
    latency_ms: int | None
    tests: int
    devices: int
    wkt: str


def url(kind: str, year: int, quarter: int) -> str:
    return SOURCE.format(kind=kind, year=year, quarter=quarter, month=(quarter - 1) * 3 + 1)


def latest(today: date) -> tuple[int, int]:
    """The latest quarter Ookla has published, a few weeks after it ends."""
    year, quarter = today.year, (today.month - 1) // 3 + 1
    for _ in range(8):
        try:
            r = httpx.head(url(KINDS[0], year, quarter), timeout=30, follow_redirects=True)
            if r.status_code == httpx.codes.OK:
                return year, quarter
        except httpx.HTTPError:
            pass
        quarter -= 1
        if quarter == 0:
            year, quarter = year - 1, 4
    raise LookupError("no published quarter found in the last two years")


def download(kind: str, year: int, quarter: int, into: Path) -> Path:
    path = into / f"ookla_{kind}_{year}Q{quarter}.parquet"
    if path.exists():
        return path
    into.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(".partial")
    with httpx.stream("GET", url(kind, year, quarter), timeout=None, follow_redirects=True) as r:
        r.raise_for_status()
        with partial.open("wb") as f:
            for chunk in r.iter_bytes():
                f.write(chunk)
    shutil.move(partial, path)
    return path


def cells(path: Path, kind: str, year: int, quarter: int) -> Iterator[Cell]:
    db = duckdb.connect()
    db.execute("set enable_progress_bar=false")
    day = date(year, (quarter - 1) * 3 + 1, 1)
    rows = db.execute(READ, [str(path), WEST, EAST, SOUTH, NORTH]).fetchall()
    for quadkey, lon, lat, down, up, latency, tests, devices in rows:
        yield Cell(
            quadkey=str(quadkey),
            family=kind,
            observed_on=day,
            down_mbps=down / 1000.0,  # kbps
            up_mbps=up / 1000.0,
            latency_ms=None if latency is None else int(latency),
            tests=int(tests),
            devices=int(devices),
            wkt=f"POINT({lon} {lat})",
        )


def write(conn: psycopg.Connection[TupleRow], found: Iterator[Cell]) -> int:
    # earlier quarters stay, so a tile getting slower shows
    conn.execute("create temp table stage_speed_cell (like speed_cell excluding indexes) on commit drop")
    n = 0
    with conn.cursor().copy(
        "copy stage_speed_cell (quadkey, family, observed_on, avg_down_mbps, avg_up_mbps, "
        "latency_ms, tests, devices, geom) from stdin"
    ) as copy:
        for c in found:
            copy.write_row((c.quadkey, c.family, c.observed_on, c.down_mbps, c.up_mbps,
                            c.latency_ms, c.tests, c.devices, c.wkt))
            n += 1

    conn.execute(
        "insert into speed_cell select * from stage_speed_cell "
        "on conflict (quadkey, family, observed_on) do update set "
        "avg_down_mbps = excluded.avg_down_mbps, avg_up_mbps = excluded.avg_up_mbps, "
        "latency_ms = excluded.latency_ms, tests = excluded.tests, devices = excluded.devices"
    )
    return n


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int)
    parser.add_argument("--quarter", type=int, choices=(1, 2, 3, 4))
    parser.add_argument("--latest", action="store_true", help="whatever they last published")
    parser.add_argument("--dir", type=Path, default=Path("data"), help="where the files are")
    parser.add_argument("--offline", action="store_true", help="fail rather than fetch")
    args = parser.parse_args(argv)

    if args.latest:
        year, quarter = latest(datetime.now(UTC).date())
    elif args.year is not None and args.quarter is not None:
        year, quarter = args.year, args.quarter
    else:
        parser.error("give --year and --quarter, or --latest")

    with connect() as conn:
        for kind in KINDS:
            path = args.dir / f"ookla_{kind}_{year}Q{quarter}.parquet"
            if not path.exists():
                if args.offline:
                    parser.error(f"{path} not found")
                path = download(kind, year, quarter, args.dir)
            n = write(conn, cells(path, kind, year, quarter))
            conn.commit()
            print(f"  ookla {kind} {year}Q{quarter}: {n} tiles loaded")
    return 0


if __name__ == "__main__":
    sys.exit(main())
