"""Cut the map tiles: streets and municipalities in one archive, measured squares in another."""

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

MIN_ZOOM = 4  # no reachable zoom may be empty
MAX_ZOOM = 14

# tippecanoe flags apply to the whole archive, not the layer they follow
COVERAGE_RULES = ("--no-feature-limit",)  # never drop a street
OVERVIEW_RULES = ("--coalesce",)  # only overview streets have identical neighbours
CELL_RULES = ("--drop-densest-as-needed",)

REGIONS_STOP = 10  # style.ts fades them out at the same zoom
FILTER = json.dumps({fields.REGIONS_LAYER: ["<=", "$zoom", REGIONS_STOP]})

# 2^10 per tile edge below DETAIL_FROM, still 2 per pixel
LOW_DETAIL = 10

CELLS_ARCHIVE = "cells.pmtiles"


def tool(name: str) -> str:
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


def layer(name: str, path: pathlib.Path) -> list[str]:
    return ["--named-layer", f"{name}:{path}"]


def cut(staged: pathlib.Path, layers: list[str], rules: list[str],
        zooms: tuple[int, int] = (MIN_ZOOM, MAX_ZOOM)) -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        [
            tool("tippecanoe"),
            "--output", str(staged),
            "--minimum-zoom", str(zooms[0]),
            "--maximum-zoom", str(zooms[1]),
            "--no-tile-size-limit",  # or it drops attributes, which are the contract
            "--preserve-input-order",
            *layers,
            *rules,
        ],
    )


def finish(*runs: subprocess.Popen[bytes]) -> None:
    failed = [r for r in runs if r.wait() != 0]
    if failed:
        raise subprocess.CalledProcessError(failed[0].returncode, failed[0].args)


def build(out: pathlib.Path, work: pathlib.Path) -> None:
    streets = work / "streets.geojsonl"
    overview = work / "streets_overview.geojsonl"
    cells = work / "cells.geojsonl"
    regions = work / "regions.geojsonl"

    # a connection per layer, all at once
    def export(layer: Callable[[psycopg.Connection[TupleRow], pathlib.Path], int], path: pathlib.Path) -> int:
        with psycopg.connect(settings.dsn) as conn:
            return layer(conn, path)

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

    # tippecanoe has one detail setting below the top zoom, so cut coarse and fine apart and join
    split = features.DETAIL_FROM
    coarse = work / "coarse.pmtiles"
    fine = work / "fine.pmtiles"
    measured = work / "measured.pmtiles"
    finish(
        cut(
            coarse,
            [
                *layer(fields.STREETS_LAYER, overview),  # same name as the fine streets
                *layer(fields.REGIONS_LAYER, regions),
            ],
            [
                *COVERAGE_RULES, *OVERVIEW_RULES,
                "--feature-filter", FILTER,
                "--low-detail", str(LOW_DETAIL), "--full-detail", str(LOW_DETAIL),
            ],
            (MIN_ZOOM, split - 1),
        ),
        cut(
            fine,
            [
                *layer(fields.STREETS_LAYER, streets),
                *layer(fields.REGIONS_LAYER, regions),
            ],
            [*COVERAGE_RULES, "--feature-filter", FILTER],
            (split, MAX_ZOOM),
        ),
        cut(measured, layer(fields.CELLS_LAYER, cells), list(CELL_RULES)),
    )

    coverage = work / "coverage.pmtiles"
    subprocess.run(
        [
            tool("tile-join"), "--quiet", "--no-tile-size-limit",
            "--output", str(coverage), str(coarse), str(fine),
        ],
        check=True,
    )

    out.parent.mkdir(parents=True, exist_ok=True)
    # work dir sits beside the output so this is an atomic rename
    for staged, name in ((coverage, out), (measured, out.parent / CELLS_ARCHIVE)):
        staged.replace(name)
        print(f"wrote {name} ({name.stat().st_size / 1_000_000:.1f} MB)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=pathlib.Path, default=pathlib.Path("tiles/speedmap.pmtiles"),
                        help="where the archive lands")
    args = parser.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=args.out.parent, prefix="publish.") as work:
        build(args.out, pathlib.Path(work))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
