from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import psycopg
import pytest
from psycopg.rows import TupleRow

from probe.decide import FRESH, INFERRED, REFUSED, UNKNOWN
from probe.lookup import verdicts

NOW = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)
RETAIL = ["TELEKOM", "VODAFONE", "NOVA"]

TABLES = "availability, address_coverage, coverage, coverage_area, address, municipality, raw_dimos"


@pytest.fixture
def street(db: psycopg.Connection[TupleRow]) -> Iterator[psycopg.Connection[TupleRow]]:
    db.execute(f"truncate {TABLES} cascade")
    db.commit()
    yield db
    db.execute(f"truncate {TABLES} cascade")
    db.execute("refresh materialized view wholesale")
    db.commit()


def _provider(conn: psycopg.Connection[TupleRow], code: str) -> int:
    row = conn.execute("select id from provider where code = %s", (code,)).fetchone()
    assert row is not None
    return int(row[0])


def _place(conn: psycopg.Connection[TupleRow], numbers: list[str]) -> list[int]:
    from normalise.build import discover, run
    from tests.test_build import seed_dimos

    seed_dimos(conn)
    run(conn, [s for s in discover() if s.name == "010_municipality"])
    muni = conn.execute("select id from municipality").fetchone()
    assert muni is not None
    ids = []
    for n in numbers:
        row = conn.execute(
            "insert into address (street, street_fold, street_no, municipality_id, geom, "
            "search_key, latin_key) values ('ΟΔΟΣ', 'ΟΔΟΣ', %s, %s, "
            "st_setsrid(st_point(24.05, 40.83), 4326), 'ΟΔΟΣ', 'ODOS') returning id",
            (n, muni[0]),
        ).fetchone()
        assert row is not None
        ids.append(int(row[0]))
    conn.commit()
    return ids


def _fiber(conn: psycopg.Connection[TupleRow], address_id: int, code: str) -> None:
    conn.execute(
        "insert into address_coverage (address_id, provider_id, technology, family, matched_by) "
        "values (%s, %s, 'FTTH', 'fiber', 'point')",
        (address_id, _provider(conn, code)),
    )
    conn.commit()


def _wholesale(conn: psycopg.Connection[TupleRow], infra: str, seller: str) -> None:
    # 50 is the least the view takes as a deal and not a typo
    conn.execute(
        "insert into coverage (source, source_ref, provider_id, infra_provider_id, technology, "
        "family, assertion) select 'register', 'w' || g, %s, %s, 'FTTH', 'fiber', 'declared' "
        "from generate_series(1, 50) g",
        (_provider(conn, seller), _provider(conn, infra)),
    )
    conn.execute("refresh materialized view wholesale")
    conn.commit()


def _reset(conn: psycopg.Connection[TupleRow]) -> None:
    conn.execute(f"truncate {TABLES} cascade")
    conn.execute("refresh materialized view wholesale")
    conn.commit()


def test_verdicts_street(street: psycopg.Connection[TupleRow]) -> None:
    here, neighbour = _place(street, ["10", "12"])
    _fiber(street, neighbour, "VODAFONE")
    found = verdicts(street, here, RETAIL, now=NOW)
    assert found["VODAFONE"] == INFERRED
    assert found["NOVA"] == UNKNOWN

    street.execute(
        "insert into availability (address_id, provider_id, technology, serviceable, source, "
        "assertion, observed_at, expires_at) values (%s, %s, 'FTTH', true, 'isp-live', 'declared', %s, %s)",
        (here, _provider(street, "VODAFONE"), NOW, NOW + timedelta(days=30)),
    )
    street.commit()
    assert verdicts(street, here, RETAIL, now=NOW)["VODAFONE"] == FRESH


def test_verdicts_wholesale(street: psycopg.Connection[TupleRow]) -> None:
    # Nova resells Telekom's lines
    here, neighbour = _place(street, ["10", "12"])
    _fiber(street, neighbour, "TELEKOM")
    _wholesale(street, "TELEKOM", "NOVA")
    assert verdicts(street, here, RETAIL, now=NOW)["NOVA"] == INFERRED

    # and not the other way round
    _reset(street)
    here, neighbour = _place(street, ["10", "12"])
    _fiber(street, neighbour, "NOVA")
    _wholesale(street, "TELEKOM", "NOVA")
    assert verdicts(street, here, RETAIL, now=NOW)["TELEKOM"] == UNKNOWN


def test_verdicts_scan(street: psycopg.Connection[TupleRow]) -> None:
    (here,) = _place(street, ["7"])
    street.execute("update address set checked_to = 14 where id = %s", (here,))
    street.commit()
    found = verdicts(street, here, RETAIL, now=NOW)
    assert found["TELEKOM"] == REFUSED
    assert found["VODAFONE"] == UNKNOWN
    assert found["NOVA"] == UNKNOWN
