"""Adding the addresses the operator serves that the register never filed."""

from __future__ import annotations

from collections.abc import Iterator

import psycopg
import pytest
from psycopg.rows import TupleRow

from ingest.cosmote import Checked, write
from normalise.build import Step, discover, run
from normalise.cosmote_address import build_cosmote_address

AREA_STEP = "080_cosmote_area"

INSIDE = (24.05, 40.83)

TABLES = "availability, cosmote_area, raw_cosmote, address, raw_coverpoint, municipality, raw_dimos"


@pytest.fixture
def gazetteer(db: psycopg.Connection[TupleRow]) -> Iterator[psycopg.Connection[TupleRow]]:
    db.execute(f"truncate {TABLES} cascade")
    db.commit()
    yield db
    db.execute(f"truncate {TABLES} cascade")
    db.commit()


def checked_at(
    rid: int, street: str, number: int, *, precision: str = "rooftop",
    kaek: str | None = None, lon: float = INSIDE[0], lat: float = INSIDE[1],
) -> Checked:
    return Checked(
        rid, "ΚΑΒΑΛΑΣ", "ΠΑΓΓΑΙΟΥ", "ΠΑΓΓΑΙΟ", street, number, "FBR_1G",
        "2026-08-06 05:51:55", f"POINT({lon} {lat})", precision, kaek,
    )


def area_step() -> list[Step]:
    return [s for s in discover() if s.name == AREA_STEP]


def build(conn: psycopg.Connection[TupleRow], rows: list[Checked], held: str | None) -> int:
    from tests.test_build import build_addresses, municipality_step, seed_dimos, seed_point

    if held is not None:
        seed_point(conn, "c1", held, lon=INSIDE[0], lat=INSIDE[1])
        build_addresses(conn)
    else:
        seed_dimos(conn)
        run(conn, municipality_step())
    write(conn, iter(rows))
    conn.commit()
    run(conn, area_step())
    return build_cosmote_address(conn)


def test_the_keys_match_the_register_path() -> None:
    """A scraped address is found by the same search as any other, or it is unfindable."""
    from normalise.address import parse
    from normalise.cosmote_address import keys

    (filed,) = parse("56429,Αμυγδαλιάς,11,ΕΥΚΑΡΠΙΑ")
    folded, search, latin = keys("Αμυγδαλιάς", "ΕΥΚΑΡΠΙΑ")
    assert (folded, search, latin) == (filed.street_fold, filed.search_key, filed.latin_key)


def test_a_street_the_register_never_filed_becomes_an_address(
    gazetteer: psycopg.Connection[TupleRow],
) -> None:
    """168 of the 333 municipalities have no register address at all."""
    assert build(gazetteer, [checked_at(1, "ΑΧΙΛΛΕΑ ΤΖΕΛΙΛΗ", 40)], None) == 1
    row = gazetteer.execute(
        "select street, street_no, postcode, source, search_key from address"
    ).fetchone()
    assert row == ("ΑΧΙΛΛΕΑ ΤΖΕΛΙΛΗ", "40", None, "cosmote", "ΑΧΙΛΛΕΑ ΤΖΕΛΙΛΗ ΠΑΓΓΑΙΟ")


def test_an_address_we_already_hold_is_not_duplicated(
    gazetteer: psycopg.Connection[TupleRow],
) -> None:
    """The register files a postcode and the scrape does not, so the key alone would collide."""
    assert build(gazetteer, [checked_at(1, "ΑΜΥΓΔΑΛΙΑΣ", 11)],
                 "56429,Αμυγδαλιάς,11,ΕΥΚΑΡΠΙΑ") == 0
    rows = gazetteer.execute("select source, count(*) from address group by 1").fetchall()
    assert rows == [("register", 1)]


def test_a_rooftop_beats_an_interpolated_point(
    gazetteer: psycopg.Connection[TupleRow],
) -> None:
    """Interpolation puts every number on a street at one point; a rooftop is a building."""
    build(gazetteer, [
        checked_at(1, "ΑΧΙΛΛΕΑ ΤΖΕΛΙΛΗ", 40, precision="interpolated", kaek="INTERP"),
        checked_at(2, "ΑΧΙΛΛΕΑ ΤΖΕΛΙΛΗ", 40, precision="rooftop", kaek="ROOF"),
    ], None)
    assert gazetteer.execute("select kaek from address").fetchall() == [("ROOF",)]


def test_the_same_number_twice_is_one_address(
    gazetteer: psycopg.Connection[TupleRow],
) -> None:
    """Two of the operator's areas can resolve to one municipality of ours."""
    assert build(gazetteer, [
        checked_at(1, "ΑΧΙΛΛΕΑ ΤΖΕΛΙΛΗ", 40),
        checked_at(2, "ΑΧΙΛΛΕΑ ΤΖΕΛΙΛΗ", 40),
    ], None) == 1


def test_the_step_is_re_runnable(gazetteer: psycopg.Connection[TupleRow]) -> None:
    build(gazetteer, [checked_at(1, "ΑΧΙΛΛΕΑ ΤΖΕΛΙΛΗ", 40)], None)
    gazetteer.commit()
    assert build_cosmote_address(gazetteer) == 0
    assert gazetteer.execute("select count(*) from address").fetchone() == (1,)
