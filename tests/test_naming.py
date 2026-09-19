"""Their spelling of an address, and how far it is safe to guess at one.

The scrape walked 43% of streets. For the rest the municipality is usually still known, and
that turns out to be nearly enough — the street-level half of the lookup is mostly not a
lookup: street_type is ΟΔΟΣ for 64,870 of 64,871 streets, area falls back to the
municipality, and their spelling of a street is our fold in 96% of rows.

What is left to guess is which of their municipalities ours means, and the two adapters are
not equally entitled to guess it. These tests are about that asymmetry.
"""

from __future__ import annotations

from collections.abc import Iterator

import psycopg
import pytest
from psycopg.rows import TupleRow

from probe.naming import NEARBY_M, STREET_TYPE, TRIES, Naming, naming, namings

TOUCHED = "raw_cosmote, municipality"

# Enough of a scrape row to be found. The real table is thirty gigabytes of cadastral
# polygons around these six columns.
ROW = """
insert into raw_cosmote
    (id, nomos, dimos, area, street, street_fold, street_type, street_no,
     municipality_id, plans, observed_at, geom)
values (%s, %s, %s, %s, %s, %s, %s, 1, 1, 'VDSL', now(), %s)
"""

# A point inside the test municipality, and the address we are asking about.
HERE = (24.05, 40.85)


@pytest.fixture
def scraped(db: psycopg.Connection[TupleRow]) -> Iterator[psycopg.Connection[TupleRow]]:
    db.execute(f"truncate {TOUCHED} cascade")
    db.execute(
        "insert into municipality (id, kallikratis_code, name, geom) values "
        "(1, '0000', 'ΔΗΜΟΣ ΤΕΣΤ', %s) on conflict (id) do nothing",
        ("SRID=4326;MULTIPOLYGON(((24.0 40.8, 24.1 40.8, 24.1 40.9, 24.0 40.8)))",),
    )
    db.commit()
    yield db
    db.execute(f"truncate {TOUCHED} cascade")
    db.commit()


def walk(
    conn: psycopg.Connection[TupleRow], rows: int, dimos: str, fold: str,
    area: str = "ΑΘΗΝΑ-ΚΟΛΩΝΟΣ", lon: float = 24.05, lat: float = 40.85,
) -> None:
    """`rows` addresses the scrape walked on one street in one of their municipalities."""
    for n in range(rows):
        conn.execute(ROW, (hash((dimos, fold, area, n)) % 10**9, "ΑΤΤΙΚΗΣ", dimos, area,
                           fold, fold, STREET_TYPE, f"SRID=4326;POINT({lon} {lat})"))
    conn.commit()


def guesses(conn: psycopg.Connection[TupleRow], fold: str = "ΠΑΤΗΣΙΩΝ") -> list[Naming]:
    return namings(conn, 1, fold, HERE[1], HERE[0])


def test_a_walked_street_is_exact(scraped: psycopg.Connection[TupleRow]) -> None:
    walk(scraped, 1, "ΑΘΗΝΑΙΩΝ", "ΑΧΑΡΝΩΝ")
    found = namings(scraped, 1, "ΑΧΑΡΝΩΝ", HERE[1], HERE[0])
    assert len(found) == 1
    assert found[0].exact is True
    assert found[0].metres is None


def test_an_unwalked_street_falls_back_to_the_municipality(
    scraped: psycopg.Connection[TupleRow],
) -> None:
    """Πατησίων is not in the scrape, and Αθηναίων very much is."""
    walk(scraped, 100, "ΑΘΗΝΑΙΩΝ", "ΑΧΑΡΝΩΝ")
    found = guesses(scraped)
    assert [n.dimos for n in found] == ["ΑΘΗΝΑΙΩΝ"]
    assert found[0].exact is False
    # Our fold is their spelling, 96% of the time — so it is what gets sent.
    assert found[0].street == "ΠΑΤΗΣΙΩΝ"
    assert found[0].street_type == STREET_TYPE


def test_candidates_come_back_nearest_first(
    scraped: psycopg.Connection[TupleRow],
) -> None:
    """Which is what makes the first one worth trying and the tail worth capping."""
    walk(scraped, 1, "ΑΘΗΝΑΙΩΝ", "ΑΧΑΡΝΩΝ", lon=24.0501, lat=40.8501)
    walk(scraped, 1, "ΚΑΙΣΑΡΙΑΝΗΣ", "ΑΧΑΡΝΩΝ", area="ΚΑΙΣΑΡΙΑΝΗ", lon=24.0520, lat=40.8520)
    found = guesses(scraped)
    assert [n.dimos for n in found] == ["ΑΘΗΝΑΙΩΝ", "ΚΑΙΣΑΡΙΑΝΗΣ"]
    first, second = found[0].metres, found[1].metres
    assert first is not None and second is not None
    assert first < second


def test_a_guess_carries_a_real_exchange_area(
    scraped: psycopg.Connection[TupleRow],
) -> None:
    """Their area is a telephone district and is filed on 100% of scrape rows. Standing the
    municipality's own name in for it is what a guess used to do, and it resolved nothing."""
    walk(scraped, 1, "ΑΘΗΝΑΙΩΝ", "ΑΧΑΡΝΩΝ", area="ΑΘΗΝΑ-ΠΕΔΙΟΝ ΑΡΕΩΣ")
    assert guesses(scraped)[0].area == "ΑΘΗΝΑ-ΠΕΔΙΟΝ ΑΡΕΩΣ"


def test_geocoding_noise_is_never_even_proposed(
    scraped: psycopg.Connection[TupleRow],
) -> None:
    """The scrape puts a few hundred Athens addresses in Ηγουμενίτσα. Counting them has to
    argue them away with a threshold; proximity does not offer them in the first place."""
    walk(scraped, 1, "ΑΘΗΝΑΙΩΝ", "ΑΧΑΡΝΩΝ")
    walk(scraped, 1, "ΗΓΟΥΜΕΝΙΤΣΗΣ", "ΑΧΑΡΝΩΝ", area="ΗΓΟΥΜΕΝΙΤΣΑ", lon=20.26, lat=39.50)
    assert [n.dimos for n in guesses(scraped)] == ["ΑΘΗΝΑΙΩΝ"]


def test_nothing_within_reach_is_not_a_guess(
    scraped: psycopg.Connection[TupleRow],
) -> None:
    """Every unwalked address sampled had a walked one within 500 m. One that does not is
    not being spelled from a town half an hour away."""
    walk(scraped, 1, "ΑΘΗΝΑΙΩΝ", "ΑΧΑΡΝΩΝ", lon=24.30, lat=40.85)
    assert guesses(scraped) == []
    assert NEARBY_M == 500.0


def test_the_tail_is_capped(scraped: psycopg.Connection[TupleRow]) -> None:
    """One unaskable address must not cost an unbounded number of requests."""
    for n in range(TRIES + 3):
        walk(scraped, 1, f"ΔΗΜΟΣ{n}", "ΑΧΑΡΝΩΝ", area=f"ΠΕΡΙΟΧΗ{n}",
             lon=24.05 + n / 10000, lat=40.85)
    assert len(guesses(scraped)) == TRIES


def test_a_municipality_nobody_walked_has_nothing_to_offer(
    scraped: psycopg.Connection[TupleRow],
) -> None:
    """2,771 streets are here, and no amount of guessing reaches them."""
    assert guesses(scraped) == []
    assert naming(scraped, 1, "ΠΑΤΗΣΙΩΝ") is None
