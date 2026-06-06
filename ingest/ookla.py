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
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import duckdb
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
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--quarter", type=int, required=True, choices=(1, 2, 3, 4))
    parser.add_argument("--dir", type=Path, default=Path("data"), help="where the files are")
    args = parser.parse_args(argv)

    with connect() as conn:
        for kind in KINDS:
            path = args.dir / f"ookla_{kind}_{args.year}Q{args.quarter}.parquet"
            if not path.exists():
                parser.error(f"{path} not found. Download it from {url(kind, args.year, args.quarter)}")
            written = write(conn, cells(path, kind, args.year, args.quarter))
            conn.commit()
            print(f"  ookla {kind} {args.year}Q{args.quarter}: {written} tiles loaded")
    return 0


if __name__ == "__main__":
    sys.exit(main())
