"""Gathering what the decision needs, for one address, across providers."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import psycopg
import pytest
from psycopg.rows import TupleRow

from probe.decide import FRESH, INFERRED, REFUSED, UNKNOWN
from probe.lookup import verdicts

NOW = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)
RETAIL = ["OTE", "VODAFONE", "NOVA"]

TABLES = "availability, address_coverage, coverage, coverage_area, address, municipality, raw_dimos"


@pytest.fixture
def street(db: psycopg.Connection[TupleRow]) -> Iterator[psycopg.Connection[TupleRow]]:
    db.execute(f"truncate {TABLES} cascade")
    db.commit()
    yield db
    db.execute(f"truncate {TABLES} cascade")
    db.execute("refresh materialized view wholesale")
    db.commit()


def provider(conn: psycopg.Connection[TupleRow], code: str) -> int:
    row = conn.execute("select id from provider where code = %s", (code,)).fetchone()
    assert row is not None
    return int(row[0])


def place(conn: psycopg.Connection[TupleRow], numbers: list[str]) -> list[int]:
    """A street of addresses in one municipality, returned in the order given."""
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


def give_fibre(conn: psycopg.Connection[TupleRow], address_id: int, code: str) -> None:
    conn.execute(
        "insert into address_coverage (address_id, provider_id, technology, family, matched_by) "
        "values (%s, %s, 'FTTH', 'fibre', 'point')",
        (address_id, provider(conn, code)),
    )
    conn.commit()


def make_wholesale(conn: psycopg.Connection[TupleRow], infra: str, seller: str) -> None:
    """Fifty filings, the minimum the relation counts as an agreement rather than an error."""
    conn.execute(
        "insert into coverage (source, source_ref, provider_id, infra_provider_id, technology, "
        "family, assertion) select 'register', 'w' || g, %s, %s, 'FTTH', 'fibre', 'declared' "
        "from generate_series(1, 50) g",
        (provider(conn, seller), provider(conn, infra)),
    )
    conn.execute("refresh materialized view wholesale")
    conn.commit()


def test_fibre_on_the_street_infers_for_its_owner(street: psycopg.Connection[TupleRow]) -> None:
    here, neighbour = place(street, ["10", "12"])
    give_fibre(street, neighbour, "VODAFONE")
    assert verdicts(street, here, RETAIL, now=NOW)["VODAFONE"] == INFERRED


def test_a_provider_without_the_street_is_unknown(street: psycopg.Connection[TupleRow]) -> None:
    here, neighbour = place(street, ["10", "12"])
    give_fibre(street, neighbour, "VODAFONE")
    assert verdicts(street, here, RETAIL, now=NOW)["NOVA"] == UNKNOWN


def test_a_reseller_inherits_the_street(street: psycopg.Connection[TupleRow]) -> None:
    """Nova sells over OTE, so OTE fibre on this street is Nova fibre on this street."""
    here, neighbour = place(street, ["10", "12"])
    give_fibre(street, neighbour, "OTE")
    make_wholesale(street, "OTE", "NOVA")
    assert verdicts(street, here, RETAIL, now=NOW)["NOVA"] == INFERRED


def test_inheritance_does_not_run_backwards(street: psycopg.Connection[TupleRow]) -> None:
    """Nova reselling over OTE says nothing about OTE reselling over Nova."""
    here, neighbour = place(street, ["10", "12"])
    give_fibre(street, neighbour, "NOVA")
    make_wholesale(street, "OTE", "NOVA")
    assert verdicts(street, here, RETAIL, now=NOW)["OTE"] == UNKNOWN


def test_an_answer_for_this_door_beats_the_street(street: psycopg.Connection[TupleRow]) -> None:
    here, neighbour = place(street, ["10", "12"])
    give_fibre(street, neighbour, "VODAFONE")
    street.execute(
        "insert into availability (address_id, provider_id, technology, serviceable, source, "
        "assertion, observed_at, expires_at) values (%s, %s, 'FTTH', true, 'isp-live', "
        "'declared', %s, %s)",
        (here, provider(street, "VODAFONE"), NOW, NOW + timedelta(days=30)),
    )
    street.commit()
    assert verdicts(street, here, RETAIL, now=NOW)["VODAFONE"] == FRESH


def test_only_the_scanned_provider_can_refuse(street: psycopg.Connection[TupleRow]) -> None:
    """checked_to belongs to the operator that was walked. Nobody else's silence is a no."""
    (here,) = place(street, ["7"])
    street.execute("update address set checked_to = 14 where id = %s", (here,))
    street.commit()
    found = verdicts(street, here, RETAIL, now=NOW)
    assert found["OTE"] == REFUSED
    assert found["VODAFONE"] == UNKNOWN
    assert found["NOVA"] == UNKNOWN
