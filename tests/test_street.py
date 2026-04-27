"""Grouping OSM ways into streets."""

from __future__ import annotations

from collections.abc import Iterator

import psycopg
import pytest
from psycopg.rows import TupleRow

from ingest.osm import Street as Way
from ingest.osm import write
from normalise.build import Step, discover, run

STEP = "060_street"

# Strictly inside the seed_dimos triangle. Its hypotenuse runs from (24.0, 40.8) to
# (24.1, 40.9), and ST_Contains excludes the boundary, so these sit clear of it.
INSIDE = "LINESTRING(24.04 40.805, 24.06 40.815)"
ALSO_INSIDE = "LINESTRING(24.06 40.815, 24.08 40.82)"
OUTSIDE = "LINESTRING(25.0 37.0, 25.01 37.01)"


@pytest.fixture
def streets(db: psycopg.Connection[TupleRow]) -> Iterator[psycopg.Connection[TupleRow]]:
    db.execute("truncate street, raw_osm_street, municipality, raw_dimos cascade")
    db.commit()
    yield db
    db.execute("truncate street, raw_osm_street, municipality, raw_dimos cascade")
    db.commit()


def street_step() -> list[Step]:
    return [s for s in discover() if s.name == STEP]


def build(conn: psycopg.Connection[TupleRow], ways: list[Way]) -> int:
    from tests.test_build import municipality_step, seed_dimos

    seed_dimos(conn)
    run(conn, municipality_step())
    write(conn, iter(ways))
    conn.commit()
    return run(conn, street_step())[STEP]


def rows(conn: psycopg.Connection[TupleRow]) -> list[tuple[str, int]]:
    found = conn.execute("select name, ways from street order by name").fetchall()
    return [(str(n), int(w)) for n, w in found]


def test_ways_with_one_name_become_one_street(
    streets: psycopg.Connection[TupleRow],
) -> None:
    """OSM splits a road at every junction; 10 ways is still one street."""
    ways = [Way(n, "Αχιλλέα Τζελίλη", "secondary", INSIDE) for n in (1, 2, 3)]
    assert build(streets, ways) == 1
    assert rows(streets) == [("Αχιλλέα Τζελίλη", 3)]


def test_word_order_variants_merge(streets: psycopg.Connection[TupleRow]) -> None:
    """528 real name pairs differ only in order: ΙΩΑΝΝΗ ΜΕΤΑΞΑ and ΜΕΤΑΞΑ ΙΩΑΝΝΗ."""
    ways = [
        Way(1, "Αχιλλέα Τζελίλη", "secondary", INSIDE),
        Way(2, "Τζελίλη Αχιλλέα", "secondary", ALSO_INSIDE),
    ]
    assert build(streets, ways) == 1
    assert rows(streets) == [("Αχιλλέα Τζελίλη", 2)]


def test_parodos_stays_its_own_street(streets: psycopg.Connection[TupleRow]) -> None:
    """ΠΑΡΟΔΟΣ names a different road from the one it references."""
    ways = [
        Way(1, "Αχιλλέα Τζελίλη", "secondary", INSIDE),
        Way(2, "Πάροδος Τζελίλη", "residential", ALSO_INSIDE),
    ]
    assert build(streets, ways) == 2


def test_the_same_name_in_two_municipalities_stays_apart(
    streets: psycopg.Connection[TupleRow],
) -> None:
    """Αγίου Γεωργίου exists in most towns and they are not one street."""
    ways = [
        Way(1, "Αγίου Γεωργίου", "residential", INSIDE),
        Way(2, "Αγίου Γεωργίου", "residential", OUTSIDE),
    ]
    assert build(streets, ways) == 2


def test_a_type_word_does_not_split_a_street(
    streets: psycopg.Connection[TupleRow],
) -> None:
    ways = [
        Way(1, "Λεωφόρος Αλεξάνδρας", "primary", INSIDE),
        Way(2, "Αλεξάνδρας", "primary", ALSO_INSIDE),
    ]
    assert build(streets, ways) == 1


def test_the_geometry_holds_every_way(streets: psycopg.Connection[TupleRow]) -> None:
    ways = [
        Way(1, "Αχιλλέα Τζελίλη", "secondary", INSIDE),
        Way(2, "Αχιλλέα Τζελίλη", "secondary", ALSO_INSIDE),
    ]
    build(streets, ways)
    row = streets.execute(
        "select st_geometrytype(geom::geometry), st_numgeometries(geom::geometry) from street"
    ).fetchone()
    assert row == ("ST_MultiLineString", 2)


def test_a_latin_key_is_written(streets: psycopg.Connection[TupleRow]) -> None:
    build(streets, [Way(1, "Αχιλλέα Τζελίλη", "secondary", INSIDE)])
    row = streets.execute("select name_fold, latin_key from street").fetchone()
    assert row == ("ΑΧΙΛΛΕΑ ΤΖΕΛΙΛΗ", "AXILLEA TZELILI")


def test_a_road_removed_from_the_extract_is_pruned(
    streets: psycopg.Connection[TupleRow],
) -> None:
    """not exists, not NOT IN: a null municipality would stop NOT IN pruning anything."""
    build(streets, [Way(1, "Αχιλλέα Τζελίλη", "secondary", INSIDE)])
    write(streets, iter([Way(2, "Άλλη", "residential", INSIDE)]))
    streets.commit()
    run(streets, street_step())
    assert rows(streets) == [("Άλλη", 1)]


def test_rebuilding_keeps_the_identifier(streets: psycopg.Connection[TupleRow]) -> None:
    """Street ids will appear in URLs, so a rebuild must not renumber them."""
    build(streets, [Way(1, "Αχιλλέα Τζελίλη", "secondary", INSIDE)])
    first = streets.execute("select id from street").fetchone()
    run(streets, street_step())
    assert streets.execute("select id from street").fetchone() == first
