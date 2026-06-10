"""Load named streets from an OpenStreetMap extract."""

from __future__ import annotations

import argparse
import shutil
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import httpx
import osmium
import psycopg
from psycopg.rows import TupleRow

from db.connect import connect

EXTRACT = Path("data/greece-latest.osm.pbf")
SOURCE_URL = "https://download.geofabrik.de/europe/greece-latest.osm.pbf"

# A way needs two placed nodes to be a line. Ways referencing nodes outside the extract
# are clipped at the border and are dropped rather than drawn wrong.
MIN_NODES = 2


@dataclass(frozen=True)
class Street:
    osm_id: int
    name: str
    highway: str
    wkt: str


def line_wkt(coordinates: list[tuple[float, float]]) -> str | None:
    """WKT for a line, or None when there are too few placed nodes to make one."""
    if len(coordinates) < MIN_NODES:
        return None
    points = ", ".join(f"{lon} {lat}" for lon, lat in coordinates)
    return f"LINESTRING({points})"


def streets(path: Path) -> Iterator[Street]:
    """Every named highway in the extract, with its geometry resolved."""
    processor = (
        osmium.FileProcessor(str(path), osmium.osm.NODE | osmium.osm.WAY)
        .with_locations()
        .with_filter(osmium.filter.EntityFilter(osmium.osm.WAY))
        .with_filter(osmium.filter.KeyFilter("highway"))
    )
    for way in processor:
        # The entity filter narrows this at runtime; the check states it for the type checker.
        if not isinstance(way, osmium.osm.Way):
            continue
        name = way.tags.get("name")
        highway = way.tags.get("highway")
        if not name or not highway:
            continue
        placed = [(n.lon, n.lat) for n in way.nodes if n.location.valid()]
        wkt = line_wkt(placed)
        if wkt is not None:
            yield Street(way.id, name, highway, wkt)


def write(conn: psycopg.Connection[TupleRow], found: Iterator[Street]) -> int:
    """Replace the table wholesale: an extract is a snapshot, not an increment."""
    conn.execute("truncate raw_osm_street")
    written = 0
    with conn.cursor().copy(
        "copy raw_osm_street (osm_id, name, highway, geom) from stdin"
    ) as copy:
        for street in found:
            copy.write_row((street.osm_id, street.name, street.highway, street.wkt))
            written += 1
    return written


def download(into: Path) -> Path:
    """Fetch the extract if it is not already here.

    Geofabrik rebuild it daily and it is the better part of a gigabyte, so it is fetched
    once and kept: a rebuild reads the same file rather than the same download.
    """
    if into.exists():
        return into
    into.parent.mkdir(parents=True, exist_ok=True)
    partial = into.with_suffix(".partial")
    with httpx.stream("GET", SOURCE_URL, timeout=None, follow_redirects=True) as answer:
        answer.raise_for_status()
        with partial.open("wb") as out:
            for chunk in answer.iter_bytes():
                out.write(chunk)
    # Renamed only once whole: a half-written extract parses as a small one, silently.
    shutil.move(partial, into)
    return into


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pbf", type=Path, default=EXTRACT, help=f"default: {EXTRACT}")
    parser.add_argument("--offline", action="store_true", help="fail rather than fetch")
    args = parser.parse_args(argv)

    if not args.pbf.exists():
        if args.offline:
            parser.error(f"{args.pbf} not found. Download it from {SOURCE_URL}")
        download(args.pbf)

    with connect() as conn:
        written = write(conn, streets(args.pbf))
        conn.commit()
    print(f"  osm streets: {written} rows loaded")
    return 0


if __name__ == "__main__":
    sys.exit(main())
