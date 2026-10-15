from __future__ import annotations

from collections.abc import Iterator

import psycopg
import pytest
from psycopg.rows import TupleRow

from probe.naming import NEARBY_M, STREET_TYPE, TRIES, Naming, naming, namings

TOUCHED = "raw_cosmote, municipality"

# just the columns naming reads
ROW = """
insert into raw_cosmote
    (id, nomos, dimos, area, street, street_fold, street_type, street_no,
     municipality_id, plans, observed_at, geom)
values (%s, %s, %s, %s, %s, %s, %s, 1, 1, 'VDSL', now(), %s)
"""

HERE = (24.05, 40.85)  # inside the test municipality


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


def _walk(conn: psycopg.Connection[TupleRow], rows: int, dimos: str, fold: str, area: str = "ΑΘΗΝΑ-ΚΟΛΩΝΟΣ",
          lon: float = 24.05, lat: float = 40.85) -> None:
    for n in range(rows):
        conn.execute(ROW, (hash((dimos, fold, area, n)) % 10**9, "ΑΤΤΙΚΗΣ", dimos, area,
                           fold, fold, STREET_TYPE, f"SRID=4326;POINT({lon} {lat})"))
    conn.commit()


def _guesses(conn: psycopg.Connection[TupleRow], fold: str = "ΠΑΤΗΣΙΩΝ") -> list[Naming]:
    return namings(conn, 1, fold, HERE[1], HERE[0])


def _clear(conn: psycopg.Connection[TupleRow]) -> None:
    conn.execute("truncate raw_cosmote")
    conn.commit()


def test_namings(scraped: psycopg.Connection[TupleRow]) -> None:
    # nobody walked anything here yet
    assert _guesses(scraped) == []
    assert naming(scraped, 1, "ΠΑΤΗΣΙΩΝ") is None

    _walk(scraped, 1, "ΑΘΗΝΑΙΩΝ", "ΑΧΑΡΝΩΝ")
    found = namings(scraped, 1, "ΑΧΑΡΝΩΝ", HERE[1], HERE[0])
    assert len(found) == 1
    assert found[0].exact is True
    assert found[0].metres is None

    # Πατησίων was never walked, Αθηναίων was
    _clear(scraped)
    _walk(scraped, 100, "ΑΘΗΝΑΙΩΝ", "ΑΧΑΡΝΩΝ")
    found = _guesses(scraped)
    assert [n.dimos for n in found] == ["ΑΘΗΝΑΙΩΝ"]
    assert found[0].exact is False
    assert found[0].street == "ΠΑΤΗΣΙΩΝ"  # our fold matches theirs 96% of the time
    assert found[0].street_type == STREET_TYPE


def test_namings_nearest(scraped: psycopg.Connection[TupleRow]) -> None:
    _walk(scraped, 1, "ΑΘΗΝΑΙΩΝ", "ΑΧΑΡΝΩΝ", lon=24.0501, lat=40.8501)
    _walk(scraped, 1, "ΚΑΙΣΑΡΙΑΝΗΣ", "ΑΧΑΡΝΩΝ", area="ΚΑΙΣΑΡΙΑΝΗ", lon=24.0520, lat=40.8520)
    found = _guesses(scraped)
    assert [n.dimos for n in found] == ["ΑΘΗΝΑΙΩΝ", "ΚΑΙΣΑΡΙΑΝΗΣ"]
    first, second = found[0].metres, found[1].metres
    assert first is not None and second is not None
    assert first < second

    # the area is their exchange district, not the municipality's name
    _clear(scraped)
    _walk(scraped, 1, "ΑΘΗΝΑΙΩΝ", "ΑΧΑΡΝΩΝ", area="ΑΘΗΝΑ-ΠΕΔΙΟΝ ΑΡΕΩΣ")
    assert _guesses(scraped)[0].area == "ΑΘΗΝΑ-ΠΕΔΙΟΝ ΑΡΕΩΣ"

    # the scrape geocodes some Athens addresses into Ηγουμενίτσα
    _clear(scraped)
    _walk(scraped, 1, "ΑΘΗΝΑΙΩΝ", "ΑΧΑΡΝΩΝ")
    _walk(scraped, 1, "ΗΓΟΥΜΕΝΙΤΣΗΣ", "ΑΧΑΡΝΩΝ", area="ΗΓΟΥΜΕΝΙΤΣΑ", lon=20.26, lat=39.50)
    assert [n.dimos for n in _guesses(scraped)] == ["ΑΘΗΝΑΙΩΝ"]


def test_namings_reach(scraped: psycopg.Connection[TupleRow]) -> None:
    _walk(scraped, 1, "ΑΘΗΝΑΙΩΝ", "ΑΧΑΡΝΩΝ", lon=24.30, lat=40.85)
    assert _guesses(scraped) == []
    assert NEARBY_M == 500.0

    _clear(scraped)
    for n in range(TRIES + 3):
        _walk(scraped, 1, f"ΔΗΜΟΣ{n}", "ΑΧΑΡΝΩΝ", area=f"ΠΕΡΙΟΧΗ{n}", lon=24.05 + n / 10000, lat=40.85)
    assert len(_guesses(scraped)) == TRIES
