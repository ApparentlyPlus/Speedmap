"""Load Ookla's quarterly open data for Greece.

Every other source here is an operator describing itself. This one is people measuring what
they got, and it is the only thing that can contradict a filing. The Greek picture is worth
stating plainly: 1.8M fixed tests median 60 Mbps against 519k mobile tests median 113, which
is why a mobile fallback is a real answer here rather than a consolation.

The file is a global parquet of several million tiles and is read locally: DuckDB over HTTP
range requests takes hours for the same query that takes no measurable time off disk.
"""

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

# Enough to hold the mainland, Crete, the Dodecanese and Corfu. Tiles are 600 m, so a
# generous box costs a few thousand rows and a tight one loses an island.
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


def quarter_start(year: int, quarter: int) -> date:
    return date(year, (quarter - 1) * 3 + 1, 1)


def published(kind: str, year: int, quarter: int) -> bool:
    """Whether Ookla has put this quarter out yet."""
    try:
        answer = httpx.head(url(kind, year, quarter), timeout=30, follow_redirects=True)
    except httpx.HTTPError:
        return False
    return answer.status_code == httpx.codes.OK


def latest(today: date) -> tuple[int, int]:
    """The most recent quarter they have published.

    They publish a quarter some weeks after it ends, so walking back from the current one is
    the only way to know without being told. Two years of walking is a data source that has
    stopped rather than one that is late.
    """
    year, quarter = today.year, (today.month - 1) // 3 + 1
    for _ in range(8):
        if published(KINDS[0], year, quarter):
            return year, quarter
        quarter -= 1
        if quarter == 0:
            year, quarter = year - 1, 4
    raise LookupError("no published quarter found in the last two years")


def download(kind: str, year: int, quarter: int, into: Path) -> Path:
    """Fetch a quarter if it is not already here.

    The file is a few hundred megabytes and is read locally rather than over HTTP: the same
    query against the remote parquet takes hours of range requests instead of no measurable
    time off disk.
    """
    path = into / f"ookla_{kind}_{year}Q{quarter}.parquet"
    if path.exists():
        return path
    into.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(".partial")
    with httpx.stream("GET", url(kind, year, quarter), timeout=None, follow_redirects=True) as r:
        r.raise_for_status()
        with partial.open("wb") as out:
            for chunk in r.iter_bytes():
                out.write(chunk)
    # Renamed only once whole, so an interrupted download is never read as a quarter.
    shutil.move(partial, path)
    return path


def cells(path: Path, kind: str, year: int, quarter: int) -> Iterator[Cell]:
    """Every Greek tile in one quarterly file."""
    db = duckdb.connect()
    db.execute("set enable_progress_bar=false")
    observed_on = quarter_start(year, quarter)
    rows = db.execute(READ, [str(path), WEST, EAST, SOUTH, NORTH]).fetchall()
    for quadkey, lon, lat, down, up, latency, tests, devices in rows:
        yield Cell(
            quadkey=str(quadkey),
            family=kind,
            observed_on=observed_on,
            # Ookla files kilobits; everything else here is megabits.
            down_mbps=down / 1000.0,
            up_mbps=up / 1000.0,
            latency_ms=None if latency is None else int(latency),
            tests=int(tests),
            devices=int(devices),
            wkt=f"POINT({lon} {lat})",
        )


def write(conn: psycopg.Connection[TupleRow], found: Iterator[Cell]) -> int:
    """Add a quarter. Earlier ones are kept: a tile getting slower is worth being able to see."""
    conn.execute(
        "create temp table stage_speed_cell (like speed_cell excluding indexes) on commit drop"
    )
    written = 0
    with conn.cursor().copy(
        "copy stage_speed_cell (quadkey, family, observed_on, avg_down_mbps, avg_up_mbps, "
        "latency_ms, tests, devices, geom) from stdin"
    ) as copy:
        for cell in found:
            copy.write_row((
                cell.quadkey, cell.family, cell.observed_on, cell.down_mbps, cell.up_mbps,
                cell.latency_ms, cell.tests, cell.devices, cell.wkt,
            ))
            written += 1
    conn.execute(
        "insert into speed_cell select * from stage_speed_cell "
        "on conflict (quadkey, family, observed_on) do update set "
        "avg_down_mbps = excluded.avg_down_mbps, avg_up_mbps = excluded.avg_up_mbps, "
        "latency_ms = excluded.latency_ms, tests = excluded.tests, devices = excluded.devices"
    )
    return written


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
            written = write(conn, cells(path, kind, year, quarter))
            conn.commit()
            print(f"  ookla {kind} {year}Q{quarter}: {written} tiles loaded")
    return 0


if __name__ == "__main__":
    sys.exit(main())
