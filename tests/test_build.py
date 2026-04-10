"""The derived-table build steps, which are re-runnable rather than once-only."""

from __future__ import annotations

from collections.abc import Iterator

import psycopg
import pytest
from psycopg.rows import TupleRow

from normalise.build import Step, discover, run

ADDRESS_STEP = "020_address"

TOUCHED = "municipality, raw_dimos, address, raw_coverpoint"

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


def address_step() -> list[Step]:
    return [s for s in discover() if s.name == ADDRESS_STEP]


def seed_point(
    conn: psycopg.Connection[TupleRow],
    coverid: str,
    address: str,
    *,
    lon: float = 24.05,
    lat: float = 40.83,
    prempass: int | None = 4,
    connstat: int | None = 1,
    vhcn: int | None = 1,
) -> None:
    conn.execute(
        "insert into raw_coverpoint (coverid, address, prempass, connstat, vhcn, point) "
        "values (%s, %s, %s, %s, %s, st_setsrid(st_point(%s, %s), 4326))",
        (coverid, address, prempass, connstat, vhcn, lon, lat),
    )
    conn.commit()


def build_addresses(conn: psycopg.Connection[TupleRow]) -> int:
    seed_dimos(conn)
    run(conn, municipality_step())
    return run(conn, address_step())[ADDRESS_STEP]


def test_a_point_becomes_an_address(buildable: psycopg.Connection[TupleRow]) -> None:
    seed_point(buildable, "a", "56429,Αμυγδαλιάς,11,ΕΥΚΑΡΠΙΑ")
    assert build_addresses(buildable) == 1
    row = buildable.execute(
        "select postcode, street, street_no, locality, premises from address"
    ).fetchone()
    assert row == ("56429", "Αμυγδαλιάς", "11", "ΕΥΚΑΡΠΙΑ", 4)


def test_a_corner_point_becomes_two_addresses(buildable: psycopg.Connection[TupleRow]) -> None:
    """6.43% of points carry two; both must be findable, and they share one geometry."""
    seed_point(buildable, "a", "26332,ΠΑΡΟΔΟΣ ΑΝΑΓΝΩΣΤΟΥ,10,Δ. ΠΑΤΡΕΩΝ|26332,ΑΝΑΓΝΩΣΤΟΥ,10,Δ. ΠΑΤΡΕΩΝ")
    assert build_addresses(buildable) == 2
    rows = buildable.execute("select street from address order by street").fetchall()
    assert [r[0] for r in rows] == ["ΑΝΑΓΝΩΣΤΟΥ", "ΠΑΡΟΔΟΣ ΑΝΑΓΝΩΣΤΟΥ"]


def test_the_same_address_on_two_points_collapses(buildable: psycopg.Connection[TupleRow]) -> None:
    """on conflict cannot touch one row twice in a statement, so the merge must deduplicate."""
    seed_point(buildable, "a", "56429,Αμυγδαλιάς,11,ΕΥΚΑΡΠΙΑ", prempass=4)
    seed_point(buildable, "b", "56429,Αμυγδαλιάς,11,ΕΥΚΑΡΠΙΑ", prempass=9)
    assert build_addresses(buildable) == 1
    row = buildable.execute("select premises from address").fetchone()
    assert row == (9,)


def test_the_municipality_is_resolved_from_the_point(
    buildable: psycopg.Connection[TupleRow],
) -> None:
    """The filed locality is ΕΥΚΑΡΠΙΑ; the municipality comes from the geometry."""
    seed_point(buildable, "a", "56429,Αμυγδαλιάς,11,ΕΥΚΑΡΠΙΑ")
    build_addresses(buildable)
    row = buildable.execute(
        "select a.locality, m.name from address a join municipality m on m.id = a.municipality_id"
    ).fetchone()
    assert row == ("ΕΥΚΑΡΠΙΑ", "ΔΗΜΟΣ ΠΑΓΓΑΙΟΥ")


def test_a_point_outside_every_municipality_still_gets_an_address(
    buildable: psycopg.Connection[TupleRow],
) -> None:
    """Unplaced is not unusable: the address is still searchable, just not attributed."""
    seed_point(buildable, "a", "56429,Αμυγδαλιάς,11,ΕΥΚΑΡΠΙΑ", lon=25.0, lat=37.0)
    assert build_addresses(buildable) == 1
    row = buildable.execute("select municipality_id from address").fetchone()
    assert row == (None,)


def test_absent_flags_stay_absent(buildable: psycopg.Connection[TupleRow]) -> None:
    """A missing connstat is unknown, not 'not connected'."""
    seed_point(buildable, "a", "56429,Αμυγδαλιάς,11,ΕΥΚΑΡΠΙΑ", prempass=None, connstat=None, vhcn=None)
    build_addresses(buildable)
    row = buildable.execute("select premises, connected, vhcn from address").fetchone()
    assert row == (None, None, None)


def test_a_zero_flag_is_false_not_absent(buildable: psycopg.Connection[TupleRow]) -> None:
    seed_point(buildable, "a", "56429,Αμυγδαλιάς,11,ΕΥΚΑΡΠΙΑ", connstat=0)
    build_addresses(buildable)
    row = buildable.execute("select connected from address").fetchone()
    assert row == (False,)


def test_a_point_with_no_street_yields_no_address(buildable: psycopg.Connection[TupleRow]) -> None:
    seed_point(buildable, "a", "56431,,1,ΣΤΑΥΡΟΥΠΟΛΗ")
    assert build_addresses(buildable) == 0


def test_rebuilding_refreshes_rather_than_duplicates(
    buildable: psycopg.Connection[TupleRow],
) -> None:
    seed_point(buildable, "a", "56429,Αμυγδαλιάς,11,ΕΥΚΑΡΠΙΑ")
    build_addresses(buildable)
    buildable.execute("update raw_coverpoint set prempass = 12 where coverid = 'a'")
    buildable.commit()
    run(buildable, address_step())
    row = buildable.execute("select count(*), max(premises) from address").fetchone()
    assert row == (1, 12)


def test_search_key_is_populated_for_type_ahead(buildable: psycopg.Connection[TupleRow]) -> None:
    seed_point(buildable, "a", "15123,ΛΕΩΦΟΡΟΣ ΙΩΑΝΝΗ ΚΑΠΟΔΙΣΤΡΙΟΥ,18,Δ. ΑΜΑΡΟΥΣΙΟΥ")
    build_addresses(buildable)
    row = buildable.execute("select search_key from address").fetchone()
    assert row == ("ΙΩΑΝΝΗ ΚΑΠΟΔΙΣΤΡΙΟΥ ΑΜΑΡΟΥΣΙΟΥ",)
