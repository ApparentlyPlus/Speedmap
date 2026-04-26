"""Reading named streets out of an OpenStreetMap extract."""

from __future__ import annotations

from collections.abc import Iterator

import psycopg
import pytest
from psycopg.rows import TupleRow

from ingest.osm import Street, line_wkt, write

# Αχιλλέα Τζελίλη in Lagkadas, the street the register does not name.
TZELILI = Street(4263046, "Αχιλλέα Τζελίλη", "secondary", "LINESTRING(23.05 40.75, 23.06 40.76)")


@pytest.fixture
def osm(db: psycopg.Connection[TupleRow]) -> Iterator[psycopg.Connection[TupleRow]]:
    db.execute("truncate raw_osm_street")
    db.commit()
    yield db
    db.execute("truncate raw_osm_street")
    db.commit()


def test_a_line_needs_two_placed_nodes() -> None:
    """Ways clipped at the extract border lose nodes and cannot be drawn."""
    assert line_wkt([]) is None
    assert line_wkt([(23.0, 40.0)]) is None
    assert line_wkt([(23.0, 40.0), (23.1, 40.1)]) == "LINESTRING(23.0 40.0, 23.1 40.1)"


def test_a_street_is_stored_with_its_geometry(
    osm: psycopg.Connection[TupleRow],
) -> None:
    assert write(osm, iter([TZELILI])) == 1
    row = osm.execute(
        "select osm_id, name, highway, st_srid(geom), st_numpoints(geom) from raw_osm_street"
    ).fetchone()
    assert row == (4263046, "Αχιλλέα Τζελίλη", "secondary", 4326, 2)


def test_loading_replaces_rather_than_accumulates(
    osm: psycopg.Connection[TupleRow],
) -> None:
    """An extract is a snapshot: a way deleted upstream must disappear here too."""
    write(osm, iter([TZELILI]))
    other = Street(99, "Άλλη Οδός", "residential", "LINESTRING(24.0 41.0, 24.1 41.1)")
    assert write(osm, iter([other])) == 1
    rows = osm.execute("select osm_id from raw_osm_street").fetchall()
    assert rows == [(99,)]


def test_an_empty_extract_empties_the_table(osm: psycopg.Connection[TupleRow]) -> None:
    write(osm, iter([TZELILI]))
    assert write(osm, iter([])) == 0
    assert osm.execute("select count(*) from raw_osm_street").fetchone() == (0,)


def test_the_geometry_is_searchable_spatially(osm: psycopg.Connection[TupleRow]) -> None:
    """Coverage for an OSM street is resolved by intersection, so the index must serve it."""
    write(osm, iter([TZELILI]))
    osm.commit()
    plan = osm.execute(
        "explain select osm_id from raw_osm_street "
        "where st_intersects(geom, st_setsrid(st_point(23.05, 40.75), 4326))"
    ).fetchall()
    assert any("raw_osm_street" in line for (line,) in plan)
