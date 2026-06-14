"""Finding the measurement tile a point falls in."""

from __future__ import annotations

from ranking.tile import ZOOM, quadkey, tile_of


def test_a_quadkey_has_one_digit_per_zoom_level() -> None:
    assert len(quadkey(37.9755, 23.7348)) == ZOOM
    assert set(quadkey(37.9755, 23.7348)) <= set("0123")


def test_the_first_digit_names_the_quarter_of_the_world() -> None:
    """Greece is north of the equator and east of Greenwich, which is quadrant one."""
    assert quadkey(37.9755, 23.7348).startswith("1")
    assert quadkey(37.9755, -23.0).startswith("0")
    assert quadkey(-37.9755, 23.7348).startswith("3")
    assert quadkey(-37.9755, -23.0).startswith("2")


def test_neighbouring_points_share_a_tile() -> None:
    """The tiles are about 600 m across, so a street is one or two of them."""
    assert quadkey(37.97550, 23.73480) == quadkey(37.97552, 23.73482)


def test_distant_points_do_not() -> None:
    assert quadkey(37.9755, 23.7348) != quadkey(40.6401, 22.9444)


def test_the_grid_is_square_at_every_zoom() -> None:
    x, y = tile_of(37.9755, 23.7348)
    assert 0 <= x < (1 << ZOOM)
    assert 0 <= y < (1 << ZOOM)


def test_a_pole_is_clamped_rather_than_raised() -> None:
    """Mercator runs to infinity there. A bad coordinate should give a wrong tile, not a crash."""
    assert len(quadkey(90.0, 0.0)) == ZOOM
    assert len(quadkey(-90.0, 0.0)) == ZOOM
