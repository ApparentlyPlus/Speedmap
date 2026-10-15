"""Load a scrape of Telekom's availability checker."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import psycopg
from psycopg.rows import TupleRow

from db.connect import connect

SCRAPE = Path("data/cosmote.db")

READ = """
select id, nomos, dimos, area, type, name, number, plans, timestamp,
       lat, lon, geocode_precision, kaek
from coverage
where plans is not null and plans <> ''
"""


@dataclass(frozen=True)
class Checked:
    id: int
    nomos: str
    dimos: str
    area: str | None
    street_type: str | None
    street: str
    street_no: int
    plans: str
    observed_at: str
    wkt: str | None
    geocode_precision: str | None
    kaek: str | None


def point_wkt(lat: float | None, lon: float | None) -> str | None:
    if lat is None or lon is None:
        return None
    return f"POINT({lon} {lat})"


def checked(path: Path) -> Iterator[Checked]:
    # most of the 30 GB is parcel polygons, which READ skips
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        for rid, nomos, dimos, area, kind, street, no, plans, stamp, lat, lon, prec, kaek in db.execute(READ):
            yield Checked(rid, nomos, dimos, area, kind, street, no, plans, stamp, point_wkt(lat, lon), prec, kaek)
    finally:
        db.close()


def write(conn: psycopg.Connection[TupleRow], found: Iterator[Checked]) -> int:
    # a scrape is a snapshot, replace the lot
    conn.execute("truncate raw_cosmote")
    n = 0
    with conn.cursor().copy(
        "copy raw_cosmote (id, nomos, dimos, area, street_type, street, street_no, plans, "
        "observed_at, geom, geocode_precision, kaek) from stdin"
    ) as copy:
        for c in found:
            copy.write_row((c.id, c.nomos, c.dimos, c.area, c.street_type, c.street, c.street_no, c.plans,
                            c.observed_at, c.wkt, c.geocode_precision, c.kaek))
            n += 1
    return n


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scrape", type=Path, default=SCRAPE, help=f"default: {SCRAPE}")
    args = parser.parse_args(argv)

    if not args.scrape.exists():
        parser.error(f"{args.scrape} not found")

    with connect() as conn:
        n = write(conn, checked(args.scrape))
        conn.commit()
    print(f"  cosmote: {n} rows loaded")
    return 0


if __name__ == "__main__":
    sys.exit(main())
