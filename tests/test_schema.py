"""
Vocabulary and constraints of the reference tables.
"""

from __future__ import annotations

import psycopg
import pytest
from psycopg.rows import TupleRow


def test_assertion_has_three_strengths(db: psycopg.Connection[TupleRow]) -> None:
    rows = db.execute("select unnest(enum_range(null::assertion))::text order by 1").fetchall()
    assert sorted(value for (value,) in rows) == ["declared", "inferred", "measured"]


def test_technology_vocabulary_is_seeded(db: psycopg.Connection[TupleRow]) -> None:
    rows = db.execute("select code, family from technology order by code").fetchall()
    assert dict(rows) == {
        "ADSL": "copper",
        "DOCSIS": "coax",
        "FTTH": "fibre",
        "FWA": "wireless",
        "SAT": "satellite",
        "VDSL": "copper",
        "VECT_VDSL": "copper",
    }


def test_copper_ceilings_are_recorded(db: psycopg.Connection[TupleRow]) -> None:
    """The ranker clamps to these; fibre and wireless have no physical ceiling to file."""
    rows = db.execute(
        "select code, max_plausible_mbps from technology where max_plausible_mbps is not null"
    ).fetchall()
    assert {code: int(ceiling) for code, ceiling in rows} == {
        "VECT_VDSL": 300,
        "VDSL": 100,
        "ADSL": 24,
    }


def test_provider_kind_is_constrained(tx: psycopg.Connection[TupleRow]) -> None:
    with pytest.raises(psycopg.errors.CheckViolation):
        tx.execute("insert into provider (code, display_name, kind) values ('X', 'X', 'isp')")


def test_provider_code_is_unique(tx: psycopg.Connection[TupleRow]) -> None:
    tx.execute("insert into provider (code, display_name, kind) values ('X', 'X', 'altnet')")
    with pytest.raises(psycopg.errors.UniqueViolation):
        tx.execute("insert into provider (code, display_name, kind) values ('X', 'Y', 'mno')")


def test_provider_does_not_build_its_own_network_by_default(
    tx: psycopg.Connection[TupleRow],
) -> None:
    row = tx.execute(
        "insert into provider (code, display_name, kind) values ('X', 'X', 'incumbent') "
        "returning builds_own_network"
    ).fetchone()
    assert row == (False,)


def test_technology_family_is_constrained(tx: psycopg.Connection[TupleRow]) -> None:
    with pytest.raises(psycopg.errors.CheckViolation):
        tx.execute("insert into technology (code, family) values ('LASER', 'photons')")
