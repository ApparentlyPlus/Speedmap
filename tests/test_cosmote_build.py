from __future__ import annotations

from collections.abc import Iterator

import psycopg
import pytest
from psycopg.rows import TupleRow

from ingest.cosmote import Checked, write
from normalise.address import parse
from normalise.build import run
from normalise.cosmote import add_addresses, best_plan, build_cosmote, keys

INSIDE = (24.05, 40.83)  # in the seed_dimos triangle
OUTSIDE = (25.0, 37.0)

CATALOGUE = {"ADSL_24M": (24.0, "ADSL"), "FBR_50M": (50.0, "VDSL"), "FBR_1G": (1000.0, "FTTH")}

TABLES = "availability, raw_cosmote, address, raw_coverpoint, municipality, raw_dimos"


AMYGDALIAS = "56429,Αμυγδαλιάς,11,ΕΥΚΑΡΠΙΑ"


def _reset(conn: psycopg.Connection[TupleRow]) -> None:
    conn.execute(f"truncate {TABLES} cascade")
    conn.commit()


@pytest.fixture
def scrape(db: psycopg.Connection[TupleRow]) -> Iterator[psycopg.Connection[TupleRow]]:
    _reset(db)
    yield db
    _reset(db)


def _checked(rid: int, street: str, number: int, plans: str = "FBR_1G", *, precision: str = "rooftop",
             kaek: str | None = None, lon: float = INSIDE[0], lat: float = INSIDE[1]) -> Checked:
    return Checked(rid, "ΚΑΒΑΛΑΣ", "ΠΑΓΓΑΙΟΥ", "ΠΑΓΓΑΙΟ", "ΟΔΟΣ", street, number, plans,
                   "2026-08-06 05:51:55", f"POINT({lon} {lat})", precision, kaek)


def _build(conn: psycopg.Connection[TupleRow], rows: list[Checked], held: str | None) -> int:
    from tests.test_build import build_addresses, municipality_step, seed_dimos, seed_point

    _reset(conn)
    if held is not None:
        seed_point(conn, "c1", held, lon=INSIDE[0], lat=INSIDE[1])
        build_addresses(conn)
    else:
        seed_dimos(conn)
        run(conn, municipality_step())
    write(conn, iter(rows))
    conn.commit()
    return build_cosmote(conn)


def _answers(conn: psycopg.Connection[TupleRow]) -> list[tuple[str, float]]:
    rows = conn.execute("select technology, max_down_mbps from availability order by technology").fetchall()
    return [(str(t), float(m)) for t, m in rows]


def test_best_plan() -> None:
    assert best_plan("ADSL_24M,FBR_50M,FBR_1G", CATALOGUE) == (1000.0, "FTTH")
    assert best_plan("ADSL_24M", CATALOGUE) == (24.0, "ADSL")
    # an unseen code means the catalogue changed, don't invent a speed
    assert best_plan("FBR_10G,FBR_50M", CATALOGUE) == (50.0, "VDSL")
    assert best_plan("FBR_10G", CATALOGUE) is None
    assert best_plan("", CATALOGUE) is None

    (filed,) = parse(AMYGDALIAS)
    assert keys("Αμυγδαλιάς", "ΕΥΚΑΡΠΙΑ") == (filed.street_fold, filed.search_key, filed.latin_key)


def test_catalogue(scrape: psycopg.Connection[TupleRow]) -> None:
    rows = scrape.execute(
        "select external_key, technology from plan pl join provider pr on pr.id = pl.provider_id "
        "where pr.code = 'TELEKOM' order by pl.down_mbps"
    ).fetchall()
    assert rows[0] == ("ADSL_24M", "ADSL")
    assert rows[-1] == ("FBR_3G", "FTTH")


def test_answers(scrape: psycopg.Connection[TupleRow]) -> None:
    _build(scrape, [_checked(1, "ΑΜΥΓΔΑΛΙΑΣ", 11, "FBR_1G,ADSL_24M")], AMYGDALIAS)
    assert _answers(scrape) == [("FTTH", 1000.0)]

    _build(scrape, [_checked(1, "ΑΜΥΓΔΑΛΙΑΣ", 11)], AMYGDALIAS)
    row = scrape.execute("select observed_at::date, expires_at > observed_at, source, serviceable from availability").fetchone()
    assert row is not None
    assert str(row[0]) == "2026-08-06"
    assert row[1:] == (True, "isp-live", True)
    # the register's copy has a postcode, the scrape's doesn't
    assert scrape.execute("select source, count(*) from address group by 1").fetchall() == [("register", 1)]

    # rerun after a fresh scrape updates, never piles up
    scrape.commit()
    build_cosmote(scrape)
    assert _answers(scrape) == [("FTTH", 1000.0)]
    assert scrape.execute("select count(*) from address").fetchone() == (1,)

    # a row too coarse to place itself still answers once the area is learned
    _build(scrape, [
        _checked(1, "ΑΜΥΓΔΑΛΙΑΣ", 11, "FBR_50M"),
        _checked(2, "ΑΜΥΓΔΑΛΙΑΣ", 12, "FBR_1G", precision="locality", lon=OUTSIDE[0], lat=OUTSIDE[1]),
    ], "56429,Αμυγδαλιάς,11,ΕΥΚΑΡΠΙΑ|56429,Αμυγδαλιάς,12,ΕΥΚΑΡΠΙΑ")
    assert _answers(scrape) == [("FTTH", 1000.0), ("VDSL", 50.0)]


def test_addresses(scrape: psycopg.Connection[TupleRow]) -> None:
    # 168 of 333 municipalities have no register address at all
    _build(scrape, [_checked(1, "ΑΧΙΛΛΕΑ ΤΖΕΛΙΛΗ", 40)], None)
    row = scrape.execute("select street, street_no, postcode, source, search_key from address").fetchone()
    assert row == ("ΑΧΙΛΛΕΑ ΤΖΕΛΙΛΗ", "40", None, "cosmote", "ΑΧΙΛΛΕΑ ΤΖΕΛΙΛΗ ΠΑΓΓΑΙΟ")

    _build(scrape, [
        _checked(1, "ΑΧΙΛΛΕΑ ΤΖΕΛΙΛΗ", 40, precision="interpolated", kaek="INTERP"),
        _checked(2, "ΑΧΙΛΛΕΑ ΤΖΕΛΙΛΗ", 40, precision="rooftop", kaek="ROOF"),
    ], None)
    assert scrape.execute("select kaek from address").fetchall() == [("ROOF",)]

    _reset(scrape)
    from tests.test_build import municipality_step, seed_dimos

    seed_dimos(scrape)
    run(scrape, municipality_step())
    write(scrape, iter([_checked(1, "ΑΧΙΛΛΕΑ ΤΖΕΛΙΛΗ", 40)]))
    scrape.commit()
    scrape.execute(
        "create temp table cosmote_area on commit drop as "
        "select 'ΠΑΓΓΑΙΟΥ'::text as dimos, 'ΠΑΓΓΑΙΟ'::text as area, id as municipality_id from municipality"
    )
    assert add_addresses(scrape) == 1


def test_checked_to(scrape: psycopg.Connection[TupleRow]) -> None:
    _build(scrape, [_checked(1, "ΑΜΥΓΔΑΛΙΑΣ", 11), _checked(2, "ΑΜΥΓΔΑΛΙΑΣ", 14)], AMYGDALIAS)
    rows = scrape.execute("select street_no, checked_to from address order by street_no").fetchall()
    assert rows == [("11", 14), ("14", 14)]

    # Τζελίλη 40 is served, the scan stopped at 1
    _build(scrape, [_checked(1, "ΑΧΙΛΛΕΑ ΤΖΕΛΙΛΗ", 1, "ADSL_24M")], "56429,Αχιλλέα Τζελίλη,40,ΠΑΓΓΑΙΟ")
    rows = scrape.execute(
        "select street_no, checked_to, street_no::int > checked_to from address order by street_no::int"
    ).fetchall()
    assert rows == [("1", 1, False), ("40", 1, True)]
