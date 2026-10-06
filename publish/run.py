"""Build the map tiles, and move them into place only once complete.

Two archives, each a single file a web server can range-request: no tile server, no directory
of a million small files. Streets and municipalities go in one, measured squares in the other.
The map draws squares or streets, never both, so a shared archive had every zoom out fetching
squares nobody was looking at: at zoom 5, 679 kB of a 1.7 MB tile.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

import psycopg
from psycopg.rows import TupleRow

from db.settings import settings
from publish import features, fields

# no reachable zoom may be empty
MIN_ZOOM = 4
MAX_ZOOM = 14

# Streets are what the map is for, so they're never dropped to save room. Coarse zooms
# coalesce them instead.
STREET_RULES = ("--drop-densest-as-needed", "--coalesce-densest-as-needed")

# Merges neighbouring features whose attributes are identical. Only the overview streets ever
# are: everything else carries its own id.
MERGE = ("--coalesce",)
CELL_RULES = ("--drop-densest-as-needed",)

# 333 polygons, the only thing drawn at zooms where the whole country fits
REGION_RULES = ("--no-feature-limit", "--no-tile-size-limit")

# Where regions stop, because streets have taken over. web/src/map/style.ts fades them out
# at the same zoom.
REGIONS_STOP = 10
FILTER = json.dumps({fields.REGIONS_LAYER: ["<=", "$zoom", REGIONS_STOP]})

# Measured squares, in an archive of their own. MapLibre doesn't fetch a source no visible
# layer reads, so the coverage map downloads none of them.
CELLS_ARCHIVE = "cells.pmtiles"


def tool(name: str) -> str:
    """Path to a build tool, or an exit saying which one is missing."""
    vendored = pathlib.Path(__file__).resolve().parent.parent / "bin" / name
    if vendored.is_file():
        return str(vendored)
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


def cut(staged: pathlib.Path, layers: list[str], rules: list[str]) -> subprocess.Popen[bytes]:
    """One tippecanoe run, one archive. Returns the running process."""
    return subprocess.Popen(
        [
            tool("tippecanoe"),
            "--output", str(staged),
            "--minimum-zoom", str(MIN_ZOOM),
            "--maximum-zoom", str(MAX_ZOOM),
            # Attributes are the contract, so tippecanoe may not drop any it thinks are dull,
            # which it otherwise does to save room.
            "--no-tile-size-limit",
            "--preserve-input-order",
            *layers,
            *rules,
        ],
    )


def finish(*runs: subprocess.Popen[bytes]) -> None:
    """Wait for every cut, failing if any did."""
    failed = [run for run in runs if run.wait() != 0]
    if failed:
        raise subprocess.CalledProcessError(failed[0].returncode, failed[0].args)


def build(out: pathlib.Path, work: pathlib.Path) -> None:
    """Cut the two archives."""
    streets = work / "streets.geojsonl"
    overview = work / "streets_overview.geojsonl"
    cells = work / "cells.geojsonl"
    regions = work / "regions.geojsonl"

    # Each layer on its own connection, all four at once. They share nothing, and run one
    # after another the streets sat waiting on the cells.
    def export(
        layer: Callable[[psycopg.Connection[TupleRow], pathlib.Path], int],
        path: pathlib.Path,
    ) -> int:
        with psycopg.connect(settings.dsn) as conn:
            return layer(conn, path)

    # beside the archive: it's one shape, wanted before the first tile arrives
    edge = out.parent / "greece.json"
    with ThreadPoolExecutor(max_workers=5) as pool:
        made = {
            name: pool.submit(export, layer, path)
            for name, layer, path in (
                ("streets", features.streets, streets),
                ("overview", features.streets_overview, overview),
                ("cells", features.cells, cells),
                ("regions", features.regions, regions),
                ("outline", features.outline, edge),
            )
        }
        print(f"streets: {made['streets'].result()} features")
        print(f"overview: {made['overview'].result()} features")
        print(f"cells:   {made['cells'].result()} features")
        print(f"regions: {made['regions'].result()} features")
        print(f"outline: {made['outline'].result() / 1_000_000:.1f} MB -> {edge}")

    # The two archives share nothing, so they're cut at once. Same inputs and flags each, so
    # the same two archives.
    coverage = work / "coverage.pmtiles"
    streets_cut = cut(
        coverage,
        [
            *layer(fields.STREETS_LAYER, streets, STREET_RULES),
            # The same layer name, so the style reads one source layer at every zoom.
            *layer(fields.STREETS_LAYER, overview, MERGE),
            *layer(fields.REGIONS_LAYER, regions, REGION_RULES),
        ],
        ["--feature-filter", FILTER],
    )

    measured = work / "measured.pmtiles"
    cells_cut = cut(measured, layer(fields.CELLS_LAYER, cells, CELL_RULES), [])
    finish(streets_cut, cells_cut)

    out.parent.mkdir(parents=True, exist_ok=True)
    # atomic within one filesystem, which is why the work directory sits beside the output
    for staged, name in ((coverage, out), (measured, out.parent / CELLS_ARCHIVE)):
        staged.replace(name)
        print(f"wrote {name} ({name.stat().st_size / 1_000_000:.1f} MB)")


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
