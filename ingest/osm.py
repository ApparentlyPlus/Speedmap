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

MIN_NODES = 2  # ways cut by the extract's edge can end up with fewer


@dataclass(frozen=True)
class Street:
    osm_id: int
    name: str
    highway: str
    wkt: str


def line_wkt(coordinates: list[tuple[float, float]]) -> str | None:
    if len(coordinates) < MIN_NODES:
        return None
    return "LINESTRING(" + ", ".join(f"{lon} {lat}" for lon, lat in coordinates) + ")"


def streets(path: Path) -> Iterator[Street]:
    fp = osmium.FileProcessor(str(path), osmium.osm.NODE | osmium.osm.WAY).with_locations()
    fp = fp.with_filter(osmium.filter.EntityFilter(osmium.osm.WAY)).with_filter(osmium.filter.KeyFilter("highway"))

    for way in fp:
        if not isinstance(way, osmium.osm.Way):  # for mypy
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
    conn.execute("truncate raw_osm_street")
    n = 0
    with conn.cursor().copy("copy raw_osm_street (osm_id, name, highway, geom) from stdin") as copy:
        for s in found:
            copy.write_row((s.osm_id, s.name, s.highway, s.wkt))
            n += 1
    return n


def download(into: Path) -> Path:
    # most of a gigabyte, fetched once and kept
    if into.exists():
        return into
    into.parent.mkdir(parents=True, exist_ok=True)
    partial = into.with_suffix(".partial")
    with httpx.stream("GET", SOURCE_URL, timeout=None, follow_redirects=True) as answer:
        answer.raise_for_status()
        with partial.open("wb") as out:
            for chunk in answer.iter_bytes():
                out.write(chunk)
    # a half written extract parses fine as a smaller one
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
        n = write(conn, streets(args.pbf))
        conn.commit()
    print(f"  osm streets: {n} rows loaded")
    return 0


if __name__ == "__main__":
    sys.exit(main())
