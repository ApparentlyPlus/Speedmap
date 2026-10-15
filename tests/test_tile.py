from __future__ import annotations

from ranking.tile import ZOOM, quadkey, tile_of


def test_quadkey() -> None:
    assert len(quadkey(37.9755, 23.7348)) == ZOOM
    assert set(quadkey(37.9755, 23.7348)) <= set("0123")

    # Greece is in quadrant 1
    assert quadkey(37.9755, 23.7348).startswith("1")
    assert quadkey(37.9755, -23.0).startswith("0")
    assert quadkey(-37.9755, 23.7348).startswith("3")
    assert quadkey(-37.9755, -23.0).startswith("2")

    assert quadkey(37.97550, 23.73480) == quadkey(37.97552, 23.73482)
    assert quadkey(37.9755, 23.7348) != quadkey(40.6401, 22.9444)  # Athens, Thessaloniki


def test_tile_of() -> None:
    x, y = tile_of(37.9755, 23.7348)
    assert 0 <= x < (1 << ZOOM)
    assert 0 <= y < (1 << ZOOM)

    # clamped, not a crash
    assert len(quadkey(90.0, 0.0)) == ZOOM
    assert len(quadkey(-90.0, 0.0)) == ZOOM
