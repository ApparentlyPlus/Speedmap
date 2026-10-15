"""Cut the planetiler archives in tiles/ down to what schema/tiles.yaml lists. Safe to rerun."""

from __future__ import annotations

import argparse
import pathlib
import subprocess

from publish.fields import BASEMAP
from publish.run import tool


def slim(archive: pathlib.Path, layers: dict[str, tuple[str, ...]]) -> None:
    # tile-join keeps a field in every layer it appears in, not per layer
    fields = sorted({f for kept in layers.values() for f in kept})
    # no --include at all would keep everything
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
    parser.add_argument("--tiles", type=pathlib.Path, default=pathlib.Path("tiles"),
                        help="the directory holding the archives")
    args = parser.parse_args()

    for name, layers in BASEMAP.items():
        archive = args.tiles / name
        if not archive.is_file():  # a fresh clone has neither
            print(f"{archive}: absent, skipped")
            continue
        before = archive.stat().st_size
        slim(archive, layers)
        after = archive.stat().st_size
        print(f"{archive}: {before / 1_000_000:.0f} MB -> {after / 1_000_000:.0f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
