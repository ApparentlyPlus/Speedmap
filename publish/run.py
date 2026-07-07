"""Build the map tiles, and put them in place only once they are whole.

Two layers go to tippecanoe and come back as one PMTiles archive, which is a single file a
web server can range-request: no tile server, no directory of a million small files, and a
CDN in front of it if it ever needs one.

The archive is built under a temporary name and renamed at the end. A rename within a
filesystem is atomic, so a reader either gets the previous archive or the new one and never
a half-written one — which matters more here than usual, because the thing being replaced
is being read by every open map at the time.

tippecanoe is a build dependency, not a runtime one: tiles are cut on a desktop and copied
to the Pi, because it wants more memory than the Pi has.
"""

from __future__ import annotations

import argparse
import pathlib
import shutil
import subprocess
import tempfile

import psycopg

from db.settings import settings
from publish import features, fields

# Nothing reachable may be empty. Three separate prototype bugs were a layer that silently
# stopped drawing at some zoom, and each took longer to find than it should have because an
# empty map looks the same as a map of nothing.
MIN_ZOOM = 4
MAX_ZOOM = 14

# Streets are what the map is for, so they are never dropped to save room; the coarse zooms
# coalesce them instead. Cells are 600 m squares and may be dropped when they overlap,
# because at zoom 5 several thousand of them occupy one pixel.
STREET_RULES = ("--drop-densest-as-needed", "--coalesce-densest-as-needed")
CELL_RULES = ("--drop-densest-as-needed",)


def tool(name: str) -> str:
    """The path to a build tool, or a refusal that says which one is missing."""
    found = shutil.which(name)
    if found is None:
        raise SystemExit(
            f"{name} is not installed. Tiles are cut on a desktop and copied to the Pi; "
            f"tippecanoe wants more memory than the Pi has."
        )
    return found


def layer(name: str, path: pathlib.Path, rules: tuple[str, ...]) -> list[str]:
    return [
        "--named-layer", f"{name}:{path}",
        *rules,
    ]


def build(out: pathlib.Path, work: pathlib.Path) -> None:
    """Cut both layers into one archive."""
    streets = work / "streets.geojsonl"
    cells = work / "cells.geojsonl"

    with psycopg.connect(settings.dsn) as conn:
        print(f"streets: {features.streets(conn, streets)} features")
        print(f"cells:   {features.cells(conn, cells)} features")

    staged = work / "tiles.pmtiles"
    subprocess.run(
        [
            tool("tippecanoe"),
            "--output", str(staged),
            "--minimum-zoom", str(MIN_ZOOM),
            "--maximum-zoom", str(MAX_ZOOM),
            # Attributes are the contract; tippecanoe must not decide any of them are dull
            # enough to drop, which it will do to save room if it is allowed to.
            "--no-tile-size-limit",
            "--preserve-input-order",
            *layer(fields.STREETS_LAYER, streets, STREET_RULES),
            *layer(fields.CELLS_LAYER, cells, CELL_RULES),
        ],
        check=True,
    )

    out.parent.mkdir(parents=True, exist_ok=True)
    # Atomic within a filesystem, which is why the work directory sits beside the output.
    staged.replace(out)
    print(f"wrote {out} ({out.stat().st_size / 1_000_000:.1f} MB)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out", type=pathlib.Path, default=pathlib.Path("tiles/speedmap.pmtiles"),
        help="where the archive lands",
    )
    asked = parser.parse_args()

    asked.out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=asked.out.parent, prefix="publish.") as work:
        build(asked.out, pathlib.Path(work))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
