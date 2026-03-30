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


def test_address_requires_a_position(tx: psycopg.Connection[TupleRow]) -> None:
    """An address with no geometry cannot be mapped, so it is not an address."""
    with pytest.raises(psycopg.errors.NotNullViolation):
        tx.execute("insert into address (street, search_key) values ('ΑΧΑΡΝΩΝ', 'ΑΧΑΡΝΩΝ')")


def test_duplicate_address_without_a_postcode_is_rejected(
    tx: psycopg.Connection[TupleRow],
) -> None:
    """Uniqueness is nulls not distinct: under default semantics these would not collide."""
    insert = (
        "insert into address (street, street_no, municipality, geom, search_key) "
        "values ('ΑΧΑΡΝΩΝ', '12', 'ΑΘΗΝΑ', 'SRID=4326;POINT(23.7 37.9)', 'ΑΧΑΡΝΩΝ 12')"
    )
    tx.execute(insert)
    with pytest.raises(psycopg.errors.UniqueViolation):
        tx.execute(insert)


def test_premises_and_connection_may_be_absent(tx: psycopg.Connection[TupleRow]) -> None:
    row = tx.execute(
        "insert into address (street, geom, search_key) "
        "values ('ΑΧΑΡΝΩΝ', 'SRID=4326;POINT(23.7 37.9)', 'ΑΧΑΡΝΩΝ') "
        "returning premises, connected, vhcn"
    ).fetchone()
    assert row == (None, None, None)


def test_search_key_is_trigram_indexed(db: psycopg.Connection[TupleRow]) -> None:
    """Type-ahead is a similarity search, which needs gin_trgm_ops rather than btree."""
    rows = db.execute("select indexdef from pg_indexes where tablename = 'address'").fetchall()
    assert any("gin_trgm_ops" in definition for (definition,) in rows)


def test_address_geometry_is_spatially_indexed(db: psycopg.Connection[TupleRow]) -> None:
    rows = db.execute("select indexdef from pg_indexes where tablename = 'address'").fetchall()
    assert any("gist" in definition and "geom" in definition for (definition,) in rows)


def make_plan(conn: psycopg.Connection[TupleRow], external_key: str = "p1") -> int:
    conn.execute("insert into provider (code, display_name, kind) values ('X', 'X', 'altnet')")
    row = conn.execute(
        "insert into plan (provider_id, external_key, name, family) "
        "values ((select id from provider where code = 'X'), %s, 'Fibre 100', 'fibre') "
        "returning id",
        (external_key,),
    ).fetchone()
    assert row is not None
    return int(row[0])


def test_plan_family_is_constrained(tx: psycopg.Connection[TupleRow]) -> None:
    tx.execute("insert into provider (code, display_name, kind) values ('X', 'X', 'altnet')")
    with pytest.raises(psycopg.errors.CheckViolation):
        tx.execute(
            "insert into plan (provider_id, external_key, name, family) "
            "values ((select id from provider where code = 'X'), 'p', 'P', 'laser')"
        )


def test_hardware_requirement_is_constrained(tx: psycopg.Connection[TupleRow]) -> None:
    tx.execute("insert into provider (code, display_name, kind) values ('X', 'X', 'altnet')")
    with pytest.raises(psycopg.errors.CheckViolation):
        tx.execute(
            "insert into plan (provider_id, external_key, name, family, needs_hardware) "
            "values ((select id from provider where code = 'X'), 'p', 'P', 'mobile', 'modem')"
        )


def test_plan_speeds_and_cap_may_be_absent(tx: psycopg.Connection[TupleRow]) -> None:
    """A null cap means unlimited, which is a value rather than a missing number."""
    plan_id = make_plan(tx)
    row = tx.execute(
        "select down_mbps, up_mbps, data_cap_gb from plan where id = %s", (plan_id,)
    ).fetchone()
    assert row == (None, None, None)


def test_one_price_per_plan_per_day(tx: psycopg.Connection[TupleRow]) -> None:
    """Append-only: a second scrape on the same day is the same observation."""
    plan_id = make_plan(tx)
    insert = "insert into plan_price (plan_id, observed_on, monthly_eur) values (%s, %s, %s)"
    tx.execute(insert, (plan_id, "2026-01-01", 30))
    with pytest.raises(psycopg.errors.UniqueViolation):
        tx.execute(insert, (plan_id, "2026-01-01", 31))


def test_plan_current_serves_the_newest_observation(tx: psycopg.Connection[TupleRow]) -> None:
    plan_id = make_plan(tx)
    insert = "insert into plan_price (plan_id, observed_on, monthly_eur) values (%s, %s, %s)"
    for observed_on, monthly in [("2026-01-01", 30), ("2026-03-01", 25), ("2026-02-01", 28)]:
        tx.execute(insert, (plan_id, observed_on, monthly))

    row = tx.execute(
        "select observed_on, monthly_eur from plan_current where plan_id = %s", (plan_id,)
    ).fetchone()
    assert row is not None
    assert str(row[0]) == "2026-03-01"
    assert int(row[1]) == 25


def test_plan_current_keeps_one_row_per_plan(tx: psycopg.Connection[TupleRow]) -> None:
    plan_id = make_plan(tx)
    insert = "insert into plan_price (plan_id, observed_on, monthly_eur) values (%s, %s, %s)"
    tx.execute(insert, (plan_id, "2026-01-01", 30))
    tx.execute(insert, (plan_id, "2026-02-01", 28))

    row = tx.execute("select count(*) from plan_current").fetchone()
    assert row == (1,)
