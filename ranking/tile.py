"""Ookla tiles: zoom 16 web mercator, ~600 m across, keyed by quadkey."""

from __future__ import annotations

import math

ZOOM = 16
LIMIT = 85.05112878  # web mercator's max latitude


def tile_of(lat: float, lon: float, zoom: int = ZOOM) -> tuple[int, int]:
    n = 1 << zoom
    phi = math.radians(max(-LIMIT, min(LIMIT, lat)))
    x = int((lon + 180.0) / 360.0 * n)
    y = int((1.0 - math.asinh(math.tan(phi)) / math.pi) / 2.0 * n)
    return min(max(x, 0), n - 1), min(max(y, 0), n - 1)


def quadkey(lat: float, lon: float, zoom: int = ZOOM) -> str:
    # one base 4 digit per level, a bit from x and a bit from y, most significant first
    x, y = tile_of(lat, lon, zoom)
    s = ""
    for z in range(zoom, 0, -1):
        b = 1 << (z - 1)
        d = 0
        if x & b:
            d += 1
        if y & b:
            d += 2
        s += str(d)
    return s
