from __future__ import annotations

from collections.abc import Iterator

import psycopg
import pytest
from psycopg.rows import TupleRow

from ingest.osm import Street, line_wkt, write

# in Lagkadas, the register doesn't name it
TZELILI = Street(4263046, "Αχιλλέα Τζελίλη", "secondary", "LINESTRING(23.05 40.75, 23.06 40.76)")


@pytest.fixture
def osm(db: psycopg.Connection[TupleRow]) -> Iterator[psycopg.Connection[TupleRow]]:
    db.execute("truncate raw_osm_street")
    db.commit()
    yield db
    db.execute("truncate raw_osm_street")
    db.commit()


def test_line_wkt() -> None:
    assert line_wkt([]) is None
    assert line_wkt([(23.0, 40.0)]) is None
    assert line_wkt([(23.0, 40.0), (23.1, 40.1)]) == "LINESTRING(23.0 40.0, 23.1 40.1)"


def test_write(osm: psycopg.Connection[TupleRow]) -> None:
    assert write(osm, iter([TZELILI])) == 1
    row = osm.execute("select osm_id, name, highway, st_srid(geom), st_numpoints(geom) from raw_osm_street").fetchone()
    assert row == (4263046, "Αχιλλέα Τζελίλη", "secondary", 4326, 2)

    # a snapshot, replaces what was there
    other = Street(99, "Άλλη Οδός", "residential", "LINESTRING(24.0 41.0, 24.1 41.1)")
    assert write(osm, iter([other])) == 1
    assert osm.execute("select osm_id from raw_osm_street").fetchall() == [(99,)]

    assert write(osm, iter([])) == 0
    assert osm.execute("select count(*) from raw_osm_street").fetchone() == (0,)


def test_write_indexed(osm: psycopg.Connection[TupleRow]) -> None:
    write(osm, iter([TZELILI]))
    osm.commit()
    plan = osm.execute(
        "explain select osm_id from raw_osm_street "
        "where st_intersects(geom, st_setsrid(st_point(23.05, 40.75), 4326))"
    ).fetchall()
    assert any("raw_osm_street" in line for (line,) in plan)
