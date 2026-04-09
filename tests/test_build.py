"""The derived-table build steps, which are re-runnable rather than once-only."""

from __future__ import annotations

from collections.abc import Iterator

import psycopg
import pytest
from psycopg.rows import TupleRow

from normalise.build import Step, discover, run

TOUCHED = "municipality, raw_dimos"

# ΔΗΜΟΣ ΠΑΓΓΑΙΟΥ, simplified to a triangle. Only the projection and the copy are under test.
POLYGON = (
    '{"type": "MultiPolygon", "coordinates": '
    "[[[[24.0, 40.8], [24.1, 40.8], [24.1, 40.9], [24.0, 40.8]]]]}"
)


@pytest.fixture
def buildable(db: psycopg.Connection[TupleRow]) -> Iterator[psycopg.Connection[TupleRow]]:
    db.execute(f"truncate {TOUCHED} cascade")
    db.commit()
    yield db
    db.execute(f"truncate {TOUCHED} cascade")
    db.commit()


def seed_dimos(conn: psycopg.Connection[TupleRow], gid: int = 1, name: str = "ΔΗΜΟΣ ΠΑΓΓΑΙΟΥ") -> None:
    conn.execute(
        "insert into raw_dimos (gid, kalcode4, d1, geom4326) "
        "values (%s, '0503', %s, st_setsrid(st_geomfromgeojson(%s), 4326))",
        (gid, name, POLYGON),
    )
    conn.commit()


def municipality_step() -> list[Step]:
    return [s for s in discover() if s.name == "010_municipality"]


def test_steps_run_in_filename_order() -> None:
    names = [s.name for s in discover()]
    assert names == sorted(names)


def test_municipality_is_copied_from_raw(buildable: psycopg.Connection[TupleRow]) -> None:
    seed_dimos(buildable)
    run(buildable, municipality_step())
    row = buildable.execute("select id, kallikratis_code, name from municipality").fetchone()
    assert row == (1, "0503", "ΔΗΜΟΣ ΠΑΓΓΑΙΟΥ")


def test_the_step_is_re_runnable(buildable: psycopg.Connection[TupleRow]) -> None:
    """A step runs again after every register pull, so it must not accumulate rows."""
    seed_dimos(buildable)
    run(buildable, municipality_step())
    run(buildable, municipality_step())
    row = buildable.execute("select count(*) from municipality").fetchone()
    assert row == (1,)


def test_a_renamed_municipality_is_refreshed(buildable: psycopg.Connection[TupleRow]) -> None:
    seed_dimos(buildable)
    run(buildable, municipality_step())
    buildable.execute("update raw_dimos set d1 = 'ΔΗΜΟΣ ΑΛΛΟΣ' where gid = 1")
    buildable.commit()
    run(buildable, municipality_step())
    row = buildable.execute("select name from municipality").fetchone()
    assert row == ("ΔΗΜΟΣ ΑΛΛΟΣ",)


def test_geometry_becomes_geography(buildable: psycopg.Connection[TupleRow]) -> None:
    """Later joins are distance and containment on a sphere, not on a plane."""
    seed_dimos(buildable)
    run(buildable, municipality_step())
    row = buildable.execute(
        "select udt_name from information_schema.columns "
        "where table_name = 'municipality' and column_name = 'geom'"
    ).fetchone()
    assert row == ("geography",)


def test_a_point_inside_resolves_to_its_municipality(
    buildable: psycopg.Connection[TupleRow],
) -> None:
    seed_dimos(buildable)
    run(buildable, municipality_step())
    row = buildable.execute(
        "select name from municipality where st_intersects(geom, st_point(24.05, 40.83)::geography)"
    ).fetchone()
    assert row == ("ΔΗΜΟΣ ΠΑΓΓΑΙΟΥ",)


def test_a_point_outside_resolves_to_nothing(buildable: psycopg.Connection[TupleRow]) -> None:
    """Unplaced is a real answer; the nearest municipality would be a guess."""
    seed_dimos(buildable)
    run(buildable, municipality_step())
    row = buildable.execute(
        "select count(*) from municipality where st_intersects(geom, st_point(25.0, 37.0)::geography)"
    ).fetchone()
    assert row == (0,)
