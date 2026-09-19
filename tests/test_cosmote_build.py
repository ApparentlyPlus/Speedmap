"""Folding the operator's scrape into the address index and the answer cache."""

from __future__ import annotations

from collections.abc import Iterator

import psycopg
import pytest
from psycopg.rows import TupleRow

from ingest.cosmote import Checked, write
from normalise.build import run
from normalise.cosmote import add_addresses, best_plan, build_cosmote, keys

# Inside the seed_dimos triangle, whose hypotenuse runs (24.0, 40.8) to (24.1, 40.9).
INSIDE = (24.05, 40.83)
OUTSIDE = (25.0, 37.0)

CATALOGUE = {"ADSL_24M": (24.0, "ADSL"), "FBR_50M": (50.0, "VDSL"), "FBR_1G": (1000.0, "FTTH")}

TABLES = "availability, raw_cosmote, address, raw_coverpoint, municipality, raw_dimos"


@pytest.fixture
def scrape(db: psycopg.Connection[TupleRow]) -> Iterator[psycopg.Connection[TupleRow]]:
    db.execute(f"truncate {TABLES} cascade")
    db.commit()
    yield db
    db.execute(f"truncate {TABLES} cascade")
    db.commit()


def checked_at(
    rid: int, street: str, number: int, plans: str = "FBR_1G", *,
    precision: str = "rooftop", kaek: str | None = None,
    lon: float = INSIDE[0], lat: float = INSIDE[1],
) -> Checked:
    return Checked(
        rid, "ΚΑΒΑΛΑΣ", "ΠΑΓΓΑΙΟΥ", "ΠΑΓΓΑΙΟ", "ΟΔΟΣ", street, number, plans,
        "2026-08-06 05:51:55", f"POINT({lon} {lat})", precision, kaek,
    )


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
    return build_cosmote(conn)


def answers(conn: psycopg.Connection[TupleRow]) -> list[tuple[str, float]]:
    rows = conn.execute(
        "select technology, max_down_mbps from availability order by technology"
    ).fetchall()
    return [(str(t), float(m)) for t, m in rows]


def test_the_fastest_plan_names_the_technology() -> None:
    """Vectored copper stops short of 200 Mbps, so the top rung says what is in the ground."""
    assert best_plan("ADSL_24M,FBR_50M,FBR_1G", CATALOGUE) == (1000.0, "FTTH")
    assert best_plan("ADSL_24M", CATALOGUE) == (24.0, "ADSL")


def test_an_unknown_code_is_ignored_rather_than_guessed() -> None:
    """A code we have never seen is a catalogue change, not a speed to invent."""
    assert best_plan("FBR_10G,FBR_50M", CATALOGUE) == (50.0, "VDSL")
    assert best_plan("FBR_10G", CATALOGUE) is None
    assert best_plan("", CATALOGUE) is None


def test_the_keys_match_the_register_path() -> None:
    """A scraped address is found by the same search as any other, or it is unfindable."""
    from normalise.address import parse

    (filed,) = parse("56429,Αμυγδαλιάς,11,ΕΥΚΑΡΠΙΑ")
    assert keys("Αμυγδαλιάς", "ΕΥΚΑΡΠΙΑ") == (
        filed.street_fold, filed.search_key, filed.latin_key,
    )


def test_the_catalogue_comes_from_the_plan_table(scrape: psycopg.Connection[TupleRow]) -> None:
    """The operator's codes are plans, so they live with every other provider's."""
    rows = scrape.execute(
        "select external_key, technology from plan pl join provider pr on pr.id = pl.provider_id "
        "where pr.code = 'OTE' order by pl.down_mbps"
    ).fetchall()
    assert rows[0] == ("ADSL_24M", "ADSL")
    assert rows[-1] == ("FBR_3G", "FTTH")


def test_a_matched_address_becomes_a_cached_answer(
    scrape: psycopg.Connection[TupleRow],
) -> None:
    build(scrape, [checked_at(1, "ΑΜΥΓΔΑΛΙΑΣ", 11, "FBR_1G,ADSL_24M")],
          "56429,Αμυγδαλιάς,11,ΕΥΚΑΡΠΙΑ")
    assert answers(scrape) == [("FTTH", 1000.0)]


def test_the_answer_carries_when_it_was_asked(scrape: psycopg.Connection[TupleRow]) -> None:
    """A cached answer without an observation date cannot ever be revalidated."""
    build(scrape, [checked_at(1, "ΑΜΥΓΔΑΛΙΑΣ", 11)], "56429,Αμυγδαλιάς,11,ΕΥΚΑΡΠΙΑ")
    row = scrape.execute(
        "select observed_at::date, expires_at > observed_at, source, serviceable "
        "from availability"
    ).fetchone()
    assert row is not None
    assert str(row[0]) == "2026-08-06"
    assert row[1:] == (True, "isp-live", True)


def test_a_street_the_register_never_filed_becomes_an_address(
    scrape: psycopg.Connection[TupleRow],
) -> None:
    """168 of the 333 municipalities have no register address at all."""
    build(scrape, [checked_at(1, "ΑΧΙΛΛΕΑ ΤΖΕΛΙΛΗ", 40)], None)
    row = scrape.execute(
        "select street, street_no, postcode, source, search_key from address"
    ).fetchone()
    assert row == ("ΑΧΙΛΛΕΑ ΤΖΕΛΙΛΗ", "40", None, "cosmote", "ΑΧΙΛΛΕΑ ΤΖΕΛΙΛΗ ΠΑΓΓΑΙΟ")


def test_an_address_we_already_hold_is_not_duplicated(
    scrape: psycopg.Connection[TupleRow],
) -> None:
    """The register files a postcode and the scrape does not, so the key alone would collide."""
    build(scrape, [checked_at(1, "ΑΜΥΓΔΑΛΙΑΣ", 11)], "56429,Αμυγδαλιάς,11,ΕΥΚΑΡΠΙΑ")
    assert scrape.execute("select source, count(*) from address group by 1").fetchall() == [
        ("register", 1)
    ]


def test_a_rooftop_beats_an_interpolated_point(scrape: psycopg.Connection[TupleRow]) -> None:
    """Interpolation puts every number on a street at one point. A rooftop is a building."""
    build(scrape, [
        checked_at(1, "ΑΧΙΛΛΕΑ ΤΖΕΛΙΛΗ", 40, precision="interpolated", kaek="INTERP"),
        checked_at(2, "ΑΧΙΛΛΕΑ ΤΖΕΛΙΛΗ", 40, precision="rooftop", kaek="ROOF"),
    ], None)
    assert scrape.execute("select kaek from address").fetchall() == [("ROOF",)]


def test_a_coarse_row_still_answers_once_the_pair_is_learned(
    scrape: psycopg.Connection[TupleRow],
) -> None:
    """That is the point of learning the pair: it carries the rows that cannot place themselves."""
    build(scrape, [
        checked_at(1, "ΑΜΥΓΔΑΛΙΑΣ", 11, "FBR_50M"),
        checked_at(2, "ΑΜΥΓΔΑΛΙΑΣ", 12, "FBR_1G", precision="locality",
                   lon=OUTSIDE[0], lat=OUTSIDE[1]),
    ], "56429,Αμυγδαλιάς,11,ΕΥΚΑΡΠΙΑ|56429,Αμυγδαλιάς,12,ΕΥΚΑΡΠΙΑ")
    assert answers(scrape) == [("FTTH", 1000.0), ("VDSL", 50.0)]


def test_the_ceiling_lands_on_every_address_of_the_street(
    scrape: psycopg.Connection[TupleRow],
) -> None:
    """The probe layer asks about an address, so the address is where the ceiling belongs."""
    build(scrape, [
        checked_at(1, "ΑΜΥΓΔΑΛΙΑΣ", 11),
        checked_at(2, "ΑΜΥΓΔΑΛΙΑΣ", 14),
    ], "56429,Αμυγδαλιάς,11,ΕΥΚΑΡΠΙΑ")
    rows = scrape.execute("select street_no, checked_to from address order by street_no").fetchall()
    assert rows == [("11", 14), ("14", 14)]


def test_a_number_above_the_ceiling_is_unknown_not_refused(
    scrape: psycopg.Connection[TupleRow],
) -> None:
    """Τζελίλη 40 exists and is served. The scan stopped at 1 and never asked."""
    build(scrape, [checked_at(1, "ΑΧΙΛΛΕΑ ΤΖΕΛΙΛΗ", 1, "ADSL_24M")],
          "56429,Αχιλλέα Τζελίλη,40,ΠΑΓΓΑΙΟ")
    rows = scrape.execute(
        "select street_no, checked_to, street_no::int > checked_to from address "
        "order by street_no::int"
    ).fetchall()
    assert rows == [("1", 1, False), ("40", 1, True)]


def test_the_step_is_re_runnable(scrape: psycopg.Connection[TupleRow]) -> None:
    """Every step runs again after a fresh scrape, so it must update rather than accumulate."""
    build(scrape, [checked_at(1, "ΑΜΥΓΔΑΛΙΑΣ", 11)], "56429,Αμυγδαλιάς,11,ΕΥΚΑΡΠΙΑ")
    scrape.commit()
    build_cosmote(scrape)
    assert answers(scrape) == [("FTTH", 1000.0)]
    assert scrape.execute("select count(*) from address").fetchone() == (1,)


def test_adding_addresses_is_separable(scrape: psycopg.Connection[TupleRow]) -> None:
    """The gazetteer half must stand alone: the answers depend on it, not the reverse."""
    from tests.test_build import municipality_step, seed_dimos

    seed_dimos(scrape)
    run(scrape, municipality_step())
    write(scrape, iter([checked_at(1, "ΑΧΙΛΛΕΑ ΤΖΕΛΙΛΗ", 40)]))
    scrape.commit()
    scrape.execute(
        "create temp table cosmote_area on commit drop as "
        "select 'ΠΑΓΓΑΙΟΥ'::text as dimos, 'ΠΑΓΓΑΙΟ'::text as area, id as municipality_id "
        "from municipality"
    )
    assert add_addresses(scrape) == 1
