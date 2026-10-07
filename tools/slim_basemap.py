"""Cut the basemap and building archives down to what the map draws.

Both are built elsewhere by planetiler, which writes every layer and attribute its profile
knows. The map reads six layers of the basemap and three fields of each building, and the
rest went over the wire and through a decoder on every zoom in: over central Athens, 1.7 MB
of basemap of which the style used 227 kB. What stays is listed in schema/tiles.yaml.

Run after copying a fresh build into tiles/. A second run changes nothing, so it's safe to
repeat. Tiles come out with the same geometry and feature ids, and draw pixel for pixel the
same.
"""

from __future__ import annotations

import argparse
import pathlib
import subprocess

from publish.fields import BASEMAP
from publish.run import tool


def slim(archive: pathlib.Path, layers: dict[str, tuple[str, ...]]) -> None:
    """Rewrite one archive in place, keeping the listed layers and fields."""
    # tile-join keeps fields by name across every layer, not per layer, so a field kept for
    # one layer stays wherever else it appears
    fields = sorted({field for kept in layers.values() for field in kept})
    # with no --include it keeps everything
    keep = [f"--include={field}" for field in fields] or ["--exclude-all"]
    staged = archive.with_name(archive.stem + ".slim" + archive.suffix)
    subprocess.run(
        [
            tool("tile-join"), "--quiet", "--force", "--no-tile-size-limit",
            "--output", str(staged),
            *[f"--layer={name}" for name in layers],
            *keep,
            str(archive),
        ],
        check=True,
    )
    staged.replace(archive)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tiles", type=pathlib.Path, default=pathlib.Path("tiles"),
        help="the directory holding the archives",
    )
    asked = parser.parse_args()

    for name, layers in BASEMAP.items():
        archive = asked.tiles / name
        # a clone has neither, and the map draws without them
        if not archive.is_file():
            print(f"{archive}: absent, skipped")
            continue
        before = archive.stat().st_size
        slim(archive, layers)
        after = archive.stat().st_size
        print(f"{archive}: {before / 1_000_000:.0f} MB -> {after / 1_000_000:.0f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
