"""Which measurement tile an address falls in.

Ookla publishes at zoom 16 of the usual web map grid, tiles roughly 600 m across, keyed by
quadkey. The grid is regular, so the tile containing a point is arithmetic on the point
rather than a search through geometry: the same reason the wireless grid needs no spatial
index either.
"""

from __future__ import annotations

import math

# Ookla's own zoom. Their tiles are published at this and nothing else.
ZOOM = 16

# Web Mercator cannot represent the poles, and clamps at the latitude where the projection
# would run to infinity. Greece is nowhere near it; the clamp is here so a bad coordinate
# returns a wrong tile rather than raising out of a maths function.
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

    A quadkey is the tile's position written as one base-four digit per zoom level, each
    digit taking one bit from the column and one from the row, most significant first.
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
