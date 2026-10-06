"""Fetch the label glyphs once, so the map draws labels from our own origin.

The style used to ask fonts.openmaptiles.org for them on every page. The CSP in deploy/Caddyfile
blocks that (connect-src is 'self'), and the host now returns an HTML page for every glyph URL
anyway, so no label was drawn from a real glyph.

They come from the OpenMapTiles fonts release now, unpacked beside the tile archives and served
with them. MapLibre asks for a stack in 256-code-point ranges as labels need them, so every
range of each stack the style names is kept.
"""

from __future__ import annotations

import argparse
import io
import pathlib
import sys
import zipfile

import httpx

from db.settings import settings

RELEASE = "https://github.com/openmaptiles/fonts/releases/download/v2.0/v2.0.zip"

# the stacks web/src/map/style.ts names in text-font, one today
STACKS = ("Noto Sans Regular",)

RANGES = 256

# A glyph range is a protobuf whose first field (the stack name) is length-delimited, tag
# 0x0a. The HTML page a wrong URL returns starts with '<'.
PROTOBUF = b"\x0a"


def unpack(archive: zipfile.ZipFile, stack: str, into: pathlib.Path) -> int:
    """Every range of one stack, all refused if any one isn't glyph data."""
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
    parser.add_argument(
        "--into", type=pathlib.Path, default=pathlib.Path("tiles/fonts"),
        help="beside the tile archives, which is where the style looks",
    )
    args = parser.parse_args(argv)

    with httpx.Client(
        headers={"User-Agent": settings.user_agent}, timeout=120, follow_redirects=True
    ) as client:
        answer = client.get(RELEASE)
        answer.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(answer.content)) as archive:
        for stack in STACKS:
            print(f"  {stack}: {unpack(archive, stack, args.into)} ranges")
    return 0


if __name__ == "__main__":
    sys.exit(main())
