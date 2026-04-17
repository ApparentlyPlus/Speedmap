"""
Vocabulary and constraints of the reference tables.
"""

from __future__ import annotations

from decimal import Decimal
from itertools import pairwise

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
        "OTHER": "other",
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
    referenced = db.execute(
        "select a.attname, c.confrelid::regclass::text from pg_constraint c "
        "join unnest(c.conkey) k on true "
        "join pg_attribute a on a.attrelid = c.conrelid and a.attnum = k "
        "where c.conrelid = 'coverage_area'::regclass and c.contype = 'f' order by 1"
    ).fetchall()
    assert referenced == [
        ("infra_provider_id", "provider"),
        ("provider_id", "provider"),
        ("source", "source"),
        ("speed_band_id", "speed_band"),
        ("technology", "technology"),
    ]


def test_coverage_geometries_differ_by_shape(db: psycopg.Connection[TupleRow]) -> None:
    """Points for fibre, polygons for copper cabinets: flattening an area loses streets."""
    rows = db.execute(
        "select f_table_name, type from geography_columns "
        "where f_table_name in ('coverage', 'coverage_area') order by 1"
    ).fetchall()
    assert dict(rows) == {"coverage": "Point", "coverage_area": "MultiPolygon"}


def test_coverage_speed_may_be_absent(tx: psycopg.Connection[TupleRow]) -> None:
    """Filed without a speed is a real state, and the majority one: 73.3% of services."""
    tx.execute("insert into provider (code, display_name, kind) values ('X', 'X', 'altnet')")
    tx.execute("insert into source (name) values ('test')")
    row = tx.execute(
        "insert into coverage (source, source_ref, provider_id, technology, family, assertion) "
        "values ('test', 'a', (select id from provider where code = 'X'), "
        "'FTTH', 'fibre', 'declared') returning speed_band_id"
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
        tx.execute("insert into address (street, street_fold, search_key) values ('ΑΧΑΡΝΩΝ', 'ΑΧΑΡΝΩΝ', 'ΑΧΑΡΝΩΝ')")


def test_duplicate_address_without_a_postcode_is_rejected(
    tx: psycopg.Connection[TupleRow],
) -> None:
    """Uniqueness is nulls not distinct: under default semantics these would not collide."""
    insert = (
        "insert into address (street, street_fold, street_no, locality, geom, search_key) "
        "values ('ΑΧΑΡΝΩΝ', 'ΑΧΑΡΝΩΝ', '12', 'ΑΘΗΝΑ', 'SRID=4326;POINT(23.7 37.9)', 'ΑΧΑΡΝΩΝ 12')"
    )
    tx.execute(insert)
    with pytest.raises(psycopg.errors.UniqueViolation):
        tx.execute(insert)


def test_premises_and_connection_may_be_absent(tx: psycopg.Connection[TupleRow]) -> None:
    row = tx.execute(
        "insert into address (street, street_fold, geom, search_key) "
        "values ('ΑΧΑΡΝΩΝ', 'ΑΧΑΡΝΩΝ', 'SRID=4326;POINT(23.7 37.9)', 'ΑΧΑΡΝΩΝ') "
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


def make_address(conn: psycopg.Connection[TupleRow]) -> int:
    row = conn.execute(
        "insert into address (street, street_fold, geom, search_key) "
        "values ('ΑΧΑΡΝΩΝ', 'ΑΧΑΡΝΩΝ', 'SRID=4326;POINT(23.7 37.9)', 'ΑΧΑΡΝΩΝ') returning id"
    ).fetchone()
    assert row is not None
    return int(row[0])


def cache_row(address_id: int, technology: str = "FTTH", source: str = "register") -> str:
    return (
        "insert into availability (address_id, provider_id, technology, serviceable, "
        "source, assertion, observed_at, expires_at) values "
        f"({address_id}, (select id from provider where code = 'X'), '{technology}', "
        f"true, '{source}', 'declared', now(), now() + interval '30 days')"
    )


def test_cache_source_is_constrained(tx: psycopg.Connection[TupleRow]) -> None:
    """Only the three tiers are storable; an unlabelled answer has no trust level."""
    tx.execute("insert into provider (code, display_name, kind) values ('X', 'X', 'altnet')")
    address_id = make_address(tx)
    with pytest.raises(psycopg.errors.CheckViolation):
        tx.execute(cache_row(address_id, source="guess"))


def test_one_answer_per_address_provider_technology(tx: psycopg.Connection[TupleRow]) -> None:
    tx.execute("insert into provider (code, display_name, kind) values ('X', 'X', 'altnet')")
    address_id = make_address(tx)
    tx.execute(cache_row(address_id))
    with pytest.raises(psycopg.errors.UniqueViolation):
        tx.execute(cache_row(address_id))


def test_one_provider_may_offer_several_technologies(tx: psycopg.Connection[TupleRow]) -> None:
    """Technology is part of the key: fibre and copper at one address are two answers."""
    tx.execute("insert into provider (code, display_name, kind) values ('X', 'X', 'altnet')")
    address_id = make_address(tx)
    tx.execute(cache_row(address_id, technology="FTTH"))
    tx.execute(cache_row(address_id, technology="VDSL"))
    row = tx.execute(
        "select count(*) from availability where address_id = %s", (address_id,)
    ).fetchone()
    assert row == (2,)


def test_serviceability_cannot_be_unknown(tx: psycopg.Connection[TupleRow]) -> None:
    """A probe that failed is not written here at all, so the column is never null."""
    tx.execute("insert into provider (code, display_name, kind) values ('X', 'X', 'altnet')")
    address_id = make_address(tx)
    with pytest.raises(psycopg.errors.NotNullViolation):
        tx.execute(
            "insert into availability (address_id, provider_id, technology, source, "
            "assertion, observed_at, expires_at) values "
            f"({address_id}, (select id from provider where code = 'X'), 'FTTH', "
            "'register', 'declared', now(), now() + interval '30 days')"
        )


def test_raw_response_is_kept_for_replay(tx: psycopg.Connection[TupleRow]) -> None:
    """A broken parser is re-run against history rather than re-scraped."""
    tx.execute("insert into provider (code, display_name, kind) values ('X', 'X', 'altnet')")
    address_id = make_address(tx)
    tx.execute(cache_row(address_id))
    tx.execute(
        "update availability set raw = %s where address_id = %s",
        ('{"eligibilityResponse": []}', address_id),
    )
    row = tx.execute(
        "select raw ->> 'eligibilityResponse' from availability where address_id = %s",
        (address_id,),
    ).fetchone()
    assert row == ("[]",)


def test_expiry_index_covers_only_serviceable_rows(db: psycopg.Connection[TupleRow]) -> None:
    """The sweep re-probes live answers; unserviceable ones are not worth the index."""
    rows = db.execute("select indexdef from pg_indexes where tablename = 'availability'").fetchall()
    assert any(
        "expires_at" in definition and "WHERE serviceable" in definition for (definition,) in rows
    )


RAW_TABLES = [
    "raw_coverpoint",
    "raw_wiredservice",
    "raw_coverage_ftth",
    "raw_coverage_copper",
    "raw_geo_coverage_copper",
    "raw_provider",
    "raw_lookup",
    "raw_dimos",
]


@pytest.mark.parametrize("table", RAW_TABLES)
def test_raw_table_exists(db: psycopg.Connection[TupleRow], table: str) -> None:
    row = db.execute("select to_regclass(%s)", (table,)).fetchone()
    assert row is not None
    assert row[0] == table


def test_raw_geometries_keep_the_projection_they_arrived_in(
    db: psycopg.Connection[TupleRow],
) -> None:
    """Copper is Greek Grid and fibre is WGS84; reprojecting on the way in loses the original."""
    rows = db.execute(
        "select f_table_name || '.' || f_geometry_column, srid from geometry_columns "
        "where f_table_name like 'raw_%' order by 1"
    ).fetchall()
    assert dict(rows) == {
        "raw_coverage_copper.geom": 2100,
        "raw_coverage_ftth.geom": 4326,
        "raw_dimos.geom": 2100,
        "raw_dimos.geom4326": 4326,
        "raw_coverpoint.point": 4326,
        "raw_coverpoint.waitpoin": 0,
        "raw_geo_coverage_copper.geom": 2100,
    }


def test_register_fetch_starts_empty(tx: psycopg.Connection[TupleRow]) -> None:
    """Resume state: a dataset with no rows yet still has a row to resume from."""
    row = tx.execute(
        "insert into register_fetch (dataset) values ('coverpoint') "
        "returning fetched, total, last_key"
    ).fetchone()
    assert row == (0, None, None)


def test_raw_speeds_are_band_ids_not_megabits(tx: psycopg.Connection[TupleRow]) -> None:
    """maxdown is a lookup id: 6 means the band '100-300 Mbps', not 6 Mbps."""
    tx.execute(
        "insert into raw_lookup (table_name, id, description) "
        "values ('a4a_maxdown', 6, '100-300 Mbps')"
    )
    row = tx.execute(
        "insert into raw_wiredservice (id, coverid, maxdown) values (1, 'x', 6) returning maxdown"
    ).fetchone()
    assert row == (6,)
    described = tx.execute(
        "select description from raw_lookup where table_name = 'a4a_maxdown' and id = 6"
    ).fetchone()
    assert described == ("100-300 Mbps",)


def test_every_register_band_is_seeded(db: psycopg.Connection[TupleRow]) -> None:
    rows = db.execute("select id, label from speed_band order by id").fetchall()
    assert [r[0] for r in rows] == [1, 2, 3, 4, 5, 6, 7, 8]
    assert rows[5][1] == "100-300 Mbps"


def test_open_ended_bands_have_one_unknown_bound(db: psycopg.Connection[TupleRow]) -> None:
    """Band 1 has no floor and band 8 no ceiling; inventing either would be a lie."""
    rows = db.execute(
        "select id, min_mbps, max_mbps from speed_band where id in (1, 8) order by id"
    ).fetchall()
    assert [(r[0], r[1], r[2]) for r in rows] == [
        (1, None, Decimal("0.2")),
        (8, Decimal(1000), None),
    ]


def test_bands_tile_the_range_without_gaps(db: psycopg.Connection[TupleRow]) -> None:
    """Each band starts where the previous one ends, so no speed falls between two bands."""
    rows = db.execute(
        "select min_mbps, max_mbps from speed_band where id between 2 and 7 order by id"
    ).fetchall()
    for (_, upper), (lower, _) in pairwise(rows):
        assert upper == lower


def test_register_technology_ids_are_mapped(db: psycopg.Connection[TupleRow]) -> None:
    rows = db.execute(
        "select register_id, code from technology where register_id is not null order by register_id"
    ).fetchall()
    assert dict(rows) == {
        1: "ADSL",
        2: "VDSL",
        3: "VECT_VDSL",
        4: "FTTH",
        5: "DOCSIS",
        13: "OTHER",
    }


def test_wireless_technologies_have_no_wired_register_id(db: psycopg.Connection[TupleRow]) -> None:
    """FWA and satellite are filed elsewhere, so a null register_id is correct here."""
    rows = db.execute(
        "select code from technology where register_id is null order by code"
    ).fetchall()
    assert [r[0] for r in rows] == ["FWA", "SAT"]


def test_every_register_provider_is_known(db: psycopg.Connection[TupleRow]) -> None:
    rows = db.execute("select count(*), count(register_id) from provider").fetchone()
    assert rows == (24, 24)


def test_network_builders_match_the_register(db: psycopg.Connection[TupleRow]) -> None:
    """Exactly the operators that appear as infrprov on the register's infrastructure points."""
    rows = db.execute(
        "select code from provider where builds_own_network order by code"
    ).fetchall()
    assert [r[0] for r in rows] == [
        "FIBER2ALL",
        "FIBERGRID",
        "HCN",
        "INALAN",
        "NETFIBER",
        "OTE",
        "OTE_ULTRAFAST",
        "UNITEDFIBER",
    ]


def test_a_wholesale_builder_need_not_sell(db: psycopg.Connection[TupleRow]) -> None:
    """FIBERGRID passes 811,123 premises and files no service; Vodafone sells over its fibre."""
    row = db.execute(
        "select builds_own_network from provider where code = 'FIBERGRID'"
    ).fetchone()
    assert row == (True,)
    row = db.execute("select builds_own_network from provider where code = 'VODAFONE'").fetchone()
    assert row == (False,)


def test_coverage_records_builder_and_seller_separately(
    tx: psycopg.Connection[TupleRow],
) -> None:
    tx.execute("insert into source (name) values ('test')")
    row = tx.execute(
        "insert into coverage (source, source_ref, provider_id, infra_provider_id, "
        "technology, family, assertion) values ('test', 'a', "
        "(select id from provider where code = 'VODAFONE'), "
        "(select id from provider where code = 'FIBERGRID'), 'FTTH', 'fibre', 'declared') "
        "returning provider_id <> infra_provider_id"
    ).fetchone()
    assert row == (True,)


def test_provider_codes_are_latin(db: psycopg.Connection[TupleRow]) -> None:
    """Codes are keys used in URLs and tile fields; display_name carries the Greek."""
    rows = db.execute("select code from provider where code !~ '^[A-Z0-9_]+$'").fetchall()
    assert rows == []


def test_address_uniqueness_keys_on_the_resolved_municipality(
    db: psycopg.Connection[TupleRow],
) -> None:
    """The filed locality text is inconsistent, so it must not be part of identity."""
    row = db.execute(
        "select pg_get_constraintdef(oid) from pg_constraint where conname = 'address_key'"
    ).fetchone()
    assert row is not None
    assert "municipality_id" in row[0]
    assert "NULLS NOT DISTINCT" in row[0]
    assert "locality" not in row[0]


def test_search_key_has_a_prefix_index(db: psycopg.Connection[TupleRow]) -> None:
    """Type-ahead is a prefix search; similarity ordering scans tens of thousands of rows."""
    rows = db.execute("select indexdef from pg_indexes where tablename = 'address'").fetchall()
    assert any("text_pattern_ops" in definition for (definition,) in rows)


def test_prefix_search_uses_the_index(db: psycopg.Connection[TupleRow]) -> None:
    """text_pattern_ops matters: under a non-C collation a plain btree would not be used."""
    plan = db.execute(
        "explain select id from address where search_key like 'ΑΧΑΡΝ%' limit 8"
    ).fetchall()
    assert any("address_search_key_prefix" in line for (line,) in plan)
