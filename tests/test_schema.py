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
    """The ranker clamps to these. Fibre and wireless have no physical ceiling to file."""
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


def test_coverage_area_has_its_own_sequence(db: psycopg.Connection[TupleRow]) -> None:
    """LIKE INCLUDING ALL would have shared coverage's sequence."""
    row = db.execute("select pg_get_serial_sequence('coverage_area', 'id')").fetchone()
    assert row == ("public.coverage_area_id_seq",)


def test_coverage_area_keeps_its_foreign_keys(db: psycopg.Connection[TupleRow]) -> None:
    """LIKE does not copy foreign keys at all."""
    row = db.execute(
        "select count(*) from pg_constraint "
        "where conrelid = 'coverage_area'::regclass and contype = 'f'"
    ).fetchone()
    assert row == (3,)


def test_coverage_geometries_differ_by_shape(db: psycopg.Connection[TupleRow]) -> None:
    """Points for fibre, polygons for copper cabinets: flattening an area loses streets."""
    rows = db.execute(
        "select f_table_name, type from geography_columns "
        "where f_table_name in ('coverage', 'coverage_area') order by 1"
    ).fetchall()
    assert dict(rows) == {"coverage": "Point", "coverage_area": "MultiPolygon"}


def test_coverage_speed_may_be_absent(tx: psycopg.Connection[TupleRow]) -> None:
    """Filed without a speed is a real state, not a missing one."""
    tx.execute("insert into provider (code, display_name, kind) values ('X', 'X', 'altnet')")
    tx.execute("insert into source (name) values ('test')")
    row = tx.execute(
        "insert into coverage (source, source_ref, provider_id, technology, family, assertion) "
        "values ('test', 'a', (select id from provider where code = 'X'), "
        "'FTTH', 'fibre', 'declared') returning max_down_mbps"
    ).fetchone()
    assert row == (None,)


def test_coverage_is_unique_per_source_place_provider_technology(
    tx: psycopg.Connection[TupleRow],
) -> None:
    tx.execute("insert into provider (code, display_name, kind) values ('X', 'X', 'altnet')")
    tx.execute("insert into source (name) values ('test')")
    insert = (
        "insert into coverage (source, source_ref, provider_id, technology, family, assertion) "
        "values ('test', 'a', (select id from provider where code = 'X'), "
        "'FTTH', 'fibre', 'declared')"
    )
    tx.execute(insert)
    with pytest.raises(psycopg.errors.UniqueViolation):
        tx.execute(insert)
