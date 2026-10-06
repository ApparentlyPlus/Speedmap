"""Which Ookla tile an address falls in.

Ookla publishes at zoom 16 of the usual web map grid, tiles about 600 m across, keyed by quadkey.
"""

from __future__ import annotations

import math

# Ookla's zoom, the only one they publish
ZOOM = 16

# Web Mercator can't reach the poles, so it clamps where the projection would run to infinity.
LIMIT = 85.05112878


def tile_of(lat: float, lon: float, zoom: int = ZOOM) -> tuple[int, int]:
    """The tile column and row a point falls in."""
    side = 1 << zoom
    held = max(-LIMIT, min(LIMIT, lat))
    radians = math.radians(held)
    x = int((lon + 180.0) / 360.0 * side)
    y = int((1.0 - math.asinh(math.tan(radians)) / math.pi) / 2.0 * side)
    return min(max(x, 0), side - 1), min(max(y, 0), side - 1)


def quadkey(lat: float, lon: float, zoom: int = ZOOM) -> str:
    """The quadkey Ookla files that tile under.

    One base-four digit per zoom level, each taking one bit from the column and one from the row,
    most significant first.
    """
    x, y = tile_of(lat, lon, zoom)
    digits = []
    for level in range(zoom, 0, -1):
        bit = 1 << (level - 1)
        digit = 0
        if x & bit:
            digit += 1
        if y & bit:
            digit += 2
        digits.append(str(digit))
    return "".join(digits)
