from __future__ import annotations

from collections.abc import Iterator

import psycopg
import pytest
from psycopg.rows import TupleRow

from ingest.osm import Street as Way
from ingest.osm import write
from normalise.build import Step, discover, run

STEP = "060_street"

# clear of seed_dimos' hypotenuse, st_contains excludes the boundary
INSIDE = "LINESTRING(24.04 40.805, 24.06 40.815)"
ALSO_INSIDE = "LINESTRING(24.06 40.815, 24.08 40.82)"
OUTSIDE = "LINESTRING(25.0 37.0, 25.01 37.01)"


TABLES = "street, raw_osm_street, municipality, raw_dimos"


@pytest.fixture
def streets(db: psycopg.Connection[TupleRow]) -> Iterator[psycopg.Connection[TupleRow]]:
    _reset(db)
    yield db
    _reset(db)


def _step() -> list[Step]:
    return [s for s in discover() if s.name == STEP]


def _reset(conn: psycopg.Connection[TupleRow]) -> None:
    conn.execute(f"truncate {TABLES} cascade")
    conn.commit()


def _build(conn: psycopg.Connection[TupleRow], ways: list[Way]) -> int:
    from tests.test_build import municipality_step, seed_dimos

    _reset(conn)
    seed_dimos(conn)
    run(conn, municipality_step())
    write(conn, iter(ways))
    conn.commit()
    return run(conn, _step())[STEP]


def _rows(conn: psycopg.Connection[TupleRow]) -> list[tuple[str, int]]:
    return [(str(n), int(w)) for n, w in conn.execute("select name, ways from street order by name").fetchall()]


def test_grouping(streets: psycopg.Connection[TupleRow]) -> None:
    # OSM splits a road at every junction
    assert _build(streets, [Way(n, "Αχιλλέα Τζελίλη", "secondary", INSIDE) for n in (1, 2, 3)]) == 1
    assert _rows(streets) == [("Αχιλλέα Τζελίλη", 3)]

    # 528 real pairs differ only in word order
    ways = [Way(1, "Αχιλλέα Τζελίλη", "secondary", INSIDE), Way(2, "Τζελίλη Αχιλλέα", "secondary", ALSO_INSIDE)]
    assert _build(streets, ways) == 1
    assert _rows(streets) == [("Αχιλλέα Τζελίλη", 2)]

    ways = [Way(1, "Αχιλλέα Τζελίλη", "secondary", INSIDE), Way(2, "Πάροδος Τζελίλη", "residential", ALSO_INSIDE)]
    assert _build(streets, ways) == 2

    # one in most towns
    ways = [Way(1, "Αγίου Γεωργίου", "residential", INSIDE), Way(2, "Αγίου Γεωργίου", "residential", OUTSIDE)]
    assert _build(streets, ways) == 2

    ways = [Way(1, "Λεωφόρος Αλεξάνδρας", "primary", INSIDE), Way(2, "Αλεξάνδρας", "primary", ALSO_INSIDE)]
    assert _build(streets, ways) == 1


def test_geometry(streets: psycopg.Connection[TupleRow]) -> None:
    _build(streets, [Way(1, "Αχιλλέα Τζελίλη", "secondary", INSIDE), Way(2, "Αχιλλέα Τζελίλη", "secondary", ALSO_INSIDE)])
    row = streets.execute("select st_geometrytype(geom::geometry), st_numgeometries(geom::geometry) from street").fetchone()
    assert row == ("ST_MultiLineString", 2)

    _build(streets, [Way(1, "Αχιλλέα Τζελίλη", "secondary", INSIDE)])
    assert streets.execute("select name_fold, latin_key from street").fetchone() == ("ΑΧΙΛΛΕΑ ΤΖΕΛΙΛΗ", "AXILLEA TZELILI")


def test_rebuild(streets: psycopg.Connection[TupleRow]) -> None:
    # ids end up in URLs
    _build(streets, [Way(1, "Αχιλλέα Τζελίλη", "secondary", INSIDE)])
    first = streets.execute("select id from street").fetchone()
    run(streets, _step())
    assert streets.execute("select id from street").fetchone() == first

    # not exists, a single null municipality stops NOT IN pruning anything
    write(streets, iter([Way(2, "Άλλη", "residential", INSIDE)]))
    streets.commit()
    run(streets, _step())
    assert _rows(streets) == [("Άλλη", 1)]
