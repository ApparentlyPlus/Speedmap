"""Fetch the label glyphs from the OpenMapTiles release, to serve them beside the tiles (CSP is 'self')."""

from __future__ import annotations

import argparse
import io
import pathlib
import sys
import zipfile

import httpx

from db.settings import settings

RELEASE = "https://github.com/openmaptiles/fonts/releases/download/v2.0/v2.0.zip"

STACKS = ("Noto Sans Regular",)  # text-font in style.ts

RANGES = 256

PROTOBUF = b"\x0a"  # tag of the first field, an HTML error page starts with '<'


def unpack(archive: zipfile.ZipFile, stack: str, into: pathlib.Path) -> int:
    found = {
        name: archive.read(name)
        for name in archive.namelist()
        if name.startswith(f"{stack}/") and name.endswith(".pbf")
    }
    if len(found) != RANGES:
        raise SystemExit(f"{stack}: {len(found)} ranges in the release, expected {RANGES}")
    bad = [name for name, body in found.items() if not body.startswith(PROTOBUF)]
    if bad:
        raise SystemExit(f"{stack}: not glyph data: {', '.join(sorted(bad)[:3])}")
    for name, body in found.items():
        out = into / name
        out.parent.mkdir(parents=True, exist_ok=True)
        part = out.with_suffix(".part")
        part.write_bytes(body)
        part.replace(out)
    return len(found)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--into", type=pathlib.Path, default=pathlib.Path("tiles/fonts"),
                        help="beside the tile archives, which is where the style looks")
    args = parser.parse_args(argv)

    with httpx.Client(headers={"User-Agent": settings.user_agent}, timeout=120, follow_redirects=True) as client:
        r = client.get(RELEASE)
        r.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(r.content)) as archive:
        for stack in STACKS:
            print(f"  {stack}: {unpack(archive, stack, args.into)} ranges")
    return 0


if __name__ == "__main__":
    sys.exit(main())
