"""Load a scrape of the operator's availability checker.

The scrape carries cadastral parcel polygons that nothing here reads and that account for
almost all of its thirty gigabytes, so the columns are named rather than selected with a
star. Coordinates come from the same file: without them the operator's dimoi cannot be
matched to a municipality, because street names alone repeat across the whole country.
"""

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
    """WKT for a checked address, or None when the scrape never placed it."""
    if lat is None or lon is None:
        return None
    return f"POINT({lon} {lat})"


def checked(path: Path) -> Iterator[Checked]:
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        for row in connection.execute(READ):
            (rid, nomos, dimos, area, kind, street, number, plans, stamp,
             lat, lon, prec, kaek) = row
            yield Checked(
                rid, nomos, dimos, area, kind, street, number, plans, stamp,
                point_wkt(lat, lon), prec, kaek,
            )
    finally:
        connection.close()


def write(conn: psycopg.Connection[TupleRow], found: Iterator[Checked]) -> int:
    """Replace the table wholesale: a scrape is a snapshot, not an increment."""
    conn.execute("truncate raw_cosmote")
    written = 0
    with conn.cursor().copy(
        "copy raw_cosmote (id, nomos, dimos, area, street_type, street, street_no, plans, "
        "observed_at, geom, geocode_precision, kaek) from stdin"
    ) as copy:
        for row in found:
            copy.write_row((
                row.id, row.nomos, row.dimos, row.area, row.street_type, row.street,
                row.street_no, row.plans, row.observed_at, row.wkt,
                row.geocode_precision, row.kaek,
            ))
            written += 1
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scrape", type=Path, default=SCRAPE, help=f"default: {SCRAPE}")
    args = parser.parse_args(argv)

    if not args.scrape.exists():
        parser.error(f"{args.scrape} not found")

    with connect() as conn:
        written = write(conn, checked(args.scrape))
        conn.commit()
    print(f"  cosmote: {written} rows loaded")
    return 0


if __name__ == "__main__":
    sys.exit(main())
