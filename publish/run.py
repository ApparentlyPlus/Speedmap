"""Build the map tiles, and put them in place only once they are whole.

Two layers go to tippecanoe and come back as one PMTiles archive, which is a single file a web
server can range-request: no tile server, no directory of a million small files.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import shutil
import subprocess
import tempfile

import psycopg

from db.settings import settings
from publish import features, fields

# Nothing reachable may be empty.
MIN_ZOOM = 4
MAX_ZOOM = 14

# Streets are what the map is for, so they are never dropped to save room. The coarse zooms
# coalesce them instead.
STREET_RULES = ("--drop-densest-as-needed", "--coalesce-densest-as-needed")
CELL_RULES = ("--drop-densest-as-needed",)

# 333 polygons, and the only thing drawn at the zooms where the country fits on the screen.
REGION_RULES = ("--no-feature-limit", "--no-tile-size-limit")

# Where the regions stop, because the streets have taken over and nothing draws them above it —
# web/src/map/style.ts fades them out at the same number.
REGIONS_STOP = 10
FILTER = json.dumps({fields.REGIONS_LAYER: ["<=", "$zoom", REGIONS_STOP]})


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
    regions = work / "regions.geojsonl"

    with psycopg.connect(settings.dsn) as conn:
        print(f"streets: {features.streets(conn, streets)} features")
        print(f"cells:   {features.cells(conn, cells)} features")
        print(f"regions: {features.regions(conn, regions)} features")
        # Beside the archive rather than inside it: it is one shape, it is wanted before the
        # first tile arrives.
        edge = out.parent / "greece.json"
        print(f"outline: {features.outline(conn, edge) / 1_000_000:.1f} MB -> {edge}")

    staged = work / "tiles.pmtiles"
    subprocess.run(
        [
            tool("tippecanoe"),
            "--output", str(staged),
            "--minimum-zoom", str(MIN_ZOOM),
            "--maximum-zoom", str(MAX_ZOOM),
            # Attributes are the contract. Tippecanoe must not decide any of them are dull
            # enough to drop, which it will do to save room if it is allowed to.
            "--no-tile-size-limit",
            "--preserve-input-order",
            *layer(fields.STREETS_LAYER, streets, STREET_RULES),
            *layer(fields.CELLS_LAYER, cells, CELL_RULES),
            *layer(fields.REGIONS_LAYER, regions, REGION_RULES),
            "--feature-filter", FILTER,
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
