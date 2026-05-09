"""Matching the operator's answers to our addresses."""

from __future__ import annotations

from collections.abc import Iterator

import psycopg
import pytest
from psycopg.rows import TupleRow

from ingest.cosmote import Checked, write
from normalise.build import discover, run
from normalise.cosmote_index import best_plan, build_cosmote_index

AREA_STEP = "080_cosmote_area"

# Inside the seed_dimos triangle, whose hypotenuse runs (24.0, 40.8) to (24.1, 40.9).
INSIDE = (24.05, 40.83)
OUTSIDE = (25.0, 37.0)

CATALOGUE = {"ADSL_24M": (24.0, "ADSL"), "FBR_50M": (50.0, "VDSL"), "FBR_1G": (1000.0, "FTTH")}


@pytest.fixture
def matched(db: psycopg.Connection[TupleRow]) -> Iterator[psycopg.Connection[TupleRow]]:
    tables = (
        "availability, cosmote_area, raw_cosmote, address, raw_coverpoint, "
        "municipality, raw_dimos"
    )
    db.execute(f"truncate {tables} cascade")
    db.commit()
    yield db
    db.execute(f"truncate {tables} cascade")
    db.commit()


def checked_at(
    rid: int, street: str, number: int, plans: str, *,
    lon: float = INSIDE[0], lat: float = INSIDE[1],
    precision: str = "rooftop", area: str = "ΠΑΓΓΑΙΟ",
) -> Checked:
    return Checked(
        rid, "ΚΑΒΑΛΑΣ", "ΠΑΓΓΑΙΟΥ", area, street, number, plans,
        "2026-08-06 05:51:55", f"POINT({lon} {lat})", precision, None,
    )


def seed(conn: psycopg.Connection[TupleRow], rows: list[Checked], address: str) -> int:
    from tests.test_build import build_addresses, seed_point

    seed_point(conn, "c1", address, lon=INSIDE[0], lat=INSIDE[1])
    build_addresses(conn)
    write(conn, iter(rows))
    conn.commit()
    run(conn, [s for s in discover() if s.name == AREA_STEP])
    return build_cosmote_index(conn)


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


def test_a_matched_address_becomes_a_cached_answer(
    matched: psycopg.Connection[TupleRow],
) -> None:
    seed(matched, [checked_at(1, "ΑΜΥΓΔΑΛΙΑΣ", 11, "FBR_1G,ADSL_24M")],
         "56429,Αμυγδαλιάς,11,ΕΥΚΑΡΠΙΑ")
    assert answers(matched) == [("FTTH", 1000.0)]


def test_the_answer_carries_when_it_was_asked(
    matched: psycopg.Connection[TupleRow],
) -> None:
    """A cached answer without an observation date cannot ever be revalidated."""
    seed(matched, [checked_at(1, "ΑΜΥΓΔΑΛΙΑΣ", 11, "FBR_1G")], "56429,Αμυγδαλιάς,11,ΕΥΚΑΡΠΙΑ")
    row = matched.execute(
        "select observed_at::date, expires_at > observed_at, source, serviceable "
        "from availability"
    ).fetchone()
    assert row is not None
    assert str(row[0]) == "2026-08-06"
    assert row[1:] == (True, "isp-live", True)


def test_an_address_we_do_not_hold_is_not_invented(
    matched: psycopg.Connection[TupleRow],
) -> None:
    """Half the country has no register addresses; the operator's are not silently added."""
    n = seed(matched, [checked_at(1, "ΑΓΝΩΣΤΗ ΟΔΟΣ", 99, "FBR_1G")],
             "56429,Αμυγδαλιάς,11,ΕΥΚΑΡΠΙΑ")
    assert n == 0
    assert answers(matched) == []


def test_a_coarsely_placed_row_does_not_teach_the_crosswalk(
    matched: psycopg.Connection[TupleRow],
) -> None:
    """Locality precision drops the point in the town centre, often the wrong municipality."""
    seed(matched, [checked_at(1, "ΑΜΥΓΔΑΛΙΑΣ", 11, "FBR_1G", precision="locality",
                              lon=OUTSIDE[0], lat=OUTSIDE[1])],
         "56429,Αμυγδαλιάς,11,ΕΥΚΑΡΠΙΑ")
    assert matched.execute("select count(*) from cosmote_area").fetchone() == (0,)


def test_a_coarse_row_still_answers_once_the_pair_is_learned(
    matched: psycopg.Connection[TupleRow],
) -> None:
    """That is the point of learning the pair: it carries the rows that cannot place themselves."""
    seed(matched, [
        checked_at(1, "ΑΜΥΓΔΑΛΙΑΣ", 11, "FBR_50M"),
        checked_at(2, "ΑΜΥΓΔΑΛΙΑΣ", 12, "FBR_1G", precision="locality",
                   lon=OUTSIDE[0], lat=OUTSIDE[1]),
    ], "56429,Αμυγδαλιάς,11,ΕΥΚΑΡΠΙΑ|56429,Αμυγδαλιάς,12,ΕΥΚΑΡΠΙΑ")
    assert answers(matched) == [("FTTH", 1000.0), ("VDSL", 50.0)]


def test_the_step_is_re_runnable(matched: psycopg.Connection[TupleRow]) -> None:
    """Every step runs again after a fresh scrape, so it must update rather than accumulate."""
    seed(matched, [checked_at(1, "ΑΜΥΓΔΑΛΙΑΣ", 11, "FBR_1G")], "56429,Αμυγδαλιάς,11,ΕΥΚΑΡΠΙΑ")
    matched.commit()
    build_cosmote_index(matched)
    assert answers(matched) == [("FTTH", 1000.0)]
