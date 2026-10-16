from __future__ import annotations

import copy
import json
import subprocess
import sys
from decimal import Decimal
from itertools import pairwise
from pathlib import Path

import psycopg
import pytest
from psycopg.rows import TupleRow

from tools.openapi_schema import contract

ADDRESS = (
    "insert into address (street, street_fold, geom, search_key, latin_key) "
    "values ('ΑΧΑΡΝΩΝ', 'ΑΧΑΡΝΩΝ', 'SRID=4326;POINT(23.7 37.9)', 'ΑΧΑΡΝΩΝ', 'AXARNON')"
)
PROVIDER = "insert into provider (code, display_name, kind) values ('X', 'X', 'altnet')"
PRICE = "insert into plan_price (plan_id, observed_on, monthly_eur) values (%s, %s, %s)"
COVERAGE = (
    "insert into coverage (source, source_ref, provider_id, technology, family, assertion) "
    "values ('test', 'a', (select id from provider where code = 'X'), 'FTTH', 'fiber', 'declared')"
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
    "raw_osm_street",
    "raw_wireless_cell",
    "raw_wireless_grid",
    "raw_cosmote",
]


def _plan(conn: psycopg.Connection[TupleRow], external_key: str = "p1") -> int:
    conn.execute(PROVIDER)
    row = conn.execute(
        "insert into plan (provider_id, external_key, name, family) "
        "values ((select id from provider where code = 'X'), %s, 'Fiber 100', 'fiber') returning id",
        (external_key,),
    ).fetchone()
    assert row is not None
    return int(row[0])


def _address(conn: psycopg.Connection[TupleRow]) -> int:
    row = conn.execute(ADDRESS + " returning id").fetchone()
    assert row is not None
    return int(row[0])


def _cache(address_id: int, technology: str = "FTTH", source: str = "register") -> str:
    return (
        "insert into availability (address_id, provider_id, technology, serviceable, "
        "source, assertion, observed_at, expires_at) values "
        f"({address_id}, (select id from provider where code = 'X'), '{technology}', "
        f"true, '{source}', 'declared', now(), now() + interval '30 days')"
    )


def _indexes(conn: psycopg.Connection[TupleRow], table: str) -> list[str]:
    return [str(d) for (d,) in conn.execute("select indexdef from pg_indexes where tablename = %s", (table,)).fetchall()]


def test_vocabulary(db: psycopg.Connection[TupleRow]) -> None:
    rows = db.execute("select unnest(enum_range(null::assertion))::text order by 1").fetchall()
    assert sorted(value for (value,) in rows) == ["declared", "inferred", "measured"]

    rows = db.execute("select code, family from technology order by code").fetchall()
    assert dict(rows) == {
        "ADSL": "copper",
        "DOCSIS": "coax",
        "FTTH": "fiber",
        "FWA": "wireless",
        "MOBILE": "wireless",
        "FWA_4G": "wireless",
        "FWA_5G": "wireless",
        "SAT": "satellite",
        "VDSL": "copper",
        "VECT_VDSL": "copper",
        "OTHER": "other",
    }

    # what the ranker clamps to
    rows = db.execute("select code, max_plausible_mbps from technology where max_plausible_mbps is not null").fetchall()
    assert {code: int(ceiling) for code, ceiling in rows} == {"VECT_VDSL": 300, "VDSL": 100, "ADSL": 24}

    rows = db.execute(
        "select register_id, code from technology where register_id is not null order by register_id"
    ).fetchall()
    assert dict(rows) == {1: "ADSL", 2: "VDSL", 3: "VECT_VDSL", 4: "FTTH", 5: "DOCSIS", 13: "OTHER"}
    # FWA and satellite are filed elsewhere
    rows = db.execute("select code from technology where register_id is null order by code").fetchall()
    assert [r[0] for r in rows] == ["FWA", "FWA_4G", "FWA_5G", "MOBILE", "SAT"]


def test_speed_bands(db: psycopg.Connection[TupleRow]) -> None:
    rows = db.execute("select id, label from speed_band order by id").fetchall()
    assert [r[0] for r in rows] == [1, 2, 3, 4, 5, 6, 7, 8]
    assert rows[5][1] == "100-300 Mbps"

    rows = db.execute("select id, min_mbps, max_mbps from speed_band where id in (1, 8) order by id").fetchall()
    assert [(r[0], r[1], r[2]) for r in rows] == [(1, None, Decimal("0.2")), (8, Decimal(1000), None)]

    rows = db.execute("select min_mbps, max_mbps from speed_band where id between 2 and 7 order by id").fetchall()
    for (_, upper), (lower, _) in pairwise(rows):
        assert upper == lower


def test_providers(db: psycopg.Connection[TupleRow]) -> None:
    # Starlink reaches everywhere, so it's filed nowhere
    assert db.execute("select count(*), count(register_id) from provider where code <> 'STARLINK'").fetchone() == (24, 24)

    rows = db.execute("select code from provider where builds_own_network and register_id is not null order by code").fetchall()
    assert [r[0] for r in rows] == [
        "FIBER2ALL",
        "FIBERGRID",
        "HCN",
        "INALAN",
        "NETFIBER",
        "OTE_ULTRAFAST",
        "TELEKOM",
        "UNITEDFIBER",
    ]
    # FIBERGRID passes 811,123 premises and sells nothing, Vodafone sells over it
    assert db.execute("select builds_own_network from provider where code = 'FIBERGRID'").fetchone() == (True,)
    assert db.execute("select builds_own_network from provider where code = 'VODAFONE'").fetchone() == (False,)

    assert db.execute("select code from provider where code !~ '^[A-Z0-9_]+$'").fetchall() == []


def test_coverage_area(db: psycopg.Connection[TupleRow]) -> None:
    # LIKE INCLUDING ALL would share coverage's sequence and drop the foreign keys
    assert db.execute("select pg_get_serial_sequence('coverage_area', 'id')").fetchone() == ("public.coverage_area_id_seq",)
    referenced = db.execute(
        "select a.attname, c.confrelid::regclass::text from pg_constraint c "
        "join unnest(c.conkey) k on true "
        "join pg_attribute a on a.attrelid = c.conrelid and a.attnum = k "
        "where c.conrelid = 'coverage_area'::regclass and c.contype = 'f' order by 1"
    ).fetchall()
    assert referenced == [
        ("infra_provider_id", "provider"),
        ("normal_band_id", "speed_band"),  # a4a_nordown, caps the street figure (0055)
        ("provider_id", "provider"),
        ("source", "source"),
        ("speed_band_id", "speed_band"),
        ("technology", "technology"),
    ]

    rows = db.execute(
        "select f_table_name, type from geography_columns where f_table_name in ('coverage', 'coverage_area') order by 1"
    ).fetchall()
    assert dict(rows) == {"coverage": "Point", "coverage_area": "MultiPolygon"}


def test_indexes(db: psycopg.Connection[TupleRow]) -> None:
    address = _indexes(db, "address")
    assert any("gin_trgm_ops" in d for d in address)
    assert any("gist" in d and "geom" in d for d in address)
    assert any("text_pattern_ops" in d for d in address)
    # the sweep only re-probes live answers
    assert any("expires_at" in d and "WHERE serviceable" in d for d in _indexes(db, "availability"))

    row = db.execute("select pg_get_constraintdef(oid) from pg_constraint where conname = 'address_key'").fetchone()
    assert row is not None
    assert "municipality_id" in row[0]
    assert "NULLS NOT DISTINCT" in row[0]
    assert "locality" not in row[0]

    # text_pattern_ops, a plain btree isn't used under a non-C collation
    db.execute("set local enable_seqscan = off")
    plan = db.execute("explain select id from address where search_key like 'ΑΧΑΡΝ%' limit 8").fetchall()
    db.rollback()
    assert any("address_search_key_prefix" in line for line, in plan)


def test_raw_tables(db: psycopg.Connection[TupleRow]) -> None:
    for table in RAW_TABLES:
        row = db.execute("select to_regclass(%s)", (table,)).fetchone()
        assert row is not None
        assert row[0] == table
    for table in ("raw_wireless_cell", "raw_wireless_grid"):
        assert db.execute("select to_regclass(%s)", (table,)).fetchone() == (table,)

    # copper arrives in Greek Grid, fiber in WGS84
    rows = db.execute(
        "select f_table_name || '.' || f_geometry_column, srid from geometry_columns "
        "where f_table_name like 'raw_%' order by 1"
    ).fetchall()
    assert dict(rows) == {
        "raw_coverage_copper.geom": 2100,
        "raw_coverage_ftth.geom": 4326,
        "raw_dimos.geom": 2100,
        "raw_osm_street.geom": 4326,
        "raw_wireless_cell.geom": 2100,
        "raw_dimos.geom4326": 4326,
        "raw_coverpoint.point": 4326,
        "raw_coverpoint.waitpoin": 0,
        "raw_geo_coverage_copper.geom": 2100,
    }


def test_raw_rows(tx: psycopg.Connection[TupleRow]) -> None:
    row = tx.execute("insert into register_fetch (dataset) values ('coverpoint') returning fetched, total, last_key").fetchone()
    assert row == (0, None, None)

    # maxdown 6 is the band "100-300 Mbps", never 6 Mbps
    tx.execute("insert into raw_lookup (table_name, id, description) values ('a4a_maxdown', 6, '100-300 Mbps')")
    row = tx.execute("insert into raw_wiredservice (id, coverid, maxdown) values (1, 'x', 6) returning maxdown").fetchone()
    assert row == (6,)
    described = tx.execute("select description from raw_lookup where table_name = 'a4a_maxdown' and id = 6").fetchone()
    assert described == ("100-300 Mbps",)


def test_defaults(tx: psycopg.Connection[TupleRow]) -> None:
    row = tx.execute(
        "insert into provider (code, display_name, kind) values ('Y', 'Y', 'incumbent') returning builds_own_network"
    ).fetchone()
    assert row == (False,)

    # 73.3% of services file no speed
    tx.execute(PROVIDER)
    tx.execute("insert into source (name) values ('test')")
    assert tx.execute(COVERAGE + " returning speed_band_id").fetchone() == (None,)

    row = tx.execute(ADDRESS + " returning premises, connected, vhcn").fetchone()
    assert row == (None, None, None)

    tx.execute(
        "insert into plan (provider_id, external_key, name, family) "
        "values ((select id from provider where code = 'X'), 'p1', 'Fiber 100', 'fiber')"
    )
    # null cap is unlimited
    row = tx.execute("select down_mbps, up_mbps, data_cap_gb from plan where external_key = 'p1'").fetchone()
    assert row == (None, None, None)

    row = tx.execute(
        "insert into coverage (source, source_ref, provider_id, infra_provider_id, "
        "technology, family, assertion) values ('test', 'b', "
        "(select id from provider where code = 'VODAFONE'), "
        "(select id from provider where code = 'FIBERGRID'), 'FTTH', 'fiber', 'declared') "
        "returning provider_id <> infra_provider_id"
    ).fetchone()
    assert row == (True,)


def test_plan_current(tx: psycopg.Connection[TupleRow]) -> None:
    plan_id = _plan(tx)
    for observed_on, monthly in [("2026-01-01", 30), ("2026-03-01", 25), ("2026-02-01", 28)]:
        tx.execute(PRICE, (plan_id, observed_on, monthly))
    row = tx.execute("select observed_on, monthly_eur from plan_current where plan_id = %s", (plan_id,)).fetchone()
    assert row is not None
    assert str(row[0]) == "2026-03-01"
    assert int(row[1]) == 25
    assert tx.execute("select count(*) from plan_current").fetchone() == (1,)


def test_availability(tx: psycopg.Connection[TupleRow]) -> None:
    tx.execute(PROVIDER)
    address_id = _address(tx)
    tx.execute(_cache(address_id, technology="FTTH"))
    tx.execute(_cache(address_id, technology="VDSL"))
    assert tx.execute("select count(*) from availability where address_id = %s", (address_id,)).fetchone() == (2,)

    # kept so a broken parser can be replayed
    tx.execute("update availability set raw = %s where address_id = %s", ('{"eligibilityResponse": []}', address_id))
    row = tx.execute(
        "select raw ->> 'eligibilityResponse' from availability where address_id = %s and technology = 'FTTH'",
        (address_id,),
    ).fetchone()
    assert row == ("[]",)


# a failed statement aborts the transaction, so one violation per test


def test_bad_provider_kind(tx: psycopg.Connection[TupleRow]) -> None:
    with pytest.raises(psycopg.errors.CheckViolation):
        tx.execute("insert into provider (code, display_name, kind) values ('X', 'X', 'isp')")


def test_duplicate_provider(tx: psycopg.Connection[TupleRow]) -> None:
    tx.execute(PROVIDER)
    with pytest.raises(psycopg.errors.UniqueViolation):
        tx.execute("insert into provider (code, display_name, kind) values ('X', 'Y', 'mno')")


def test_bad_family(tx: psycopg.Connection[TupleRow]) -> None:
    with pytest.raises(psycopg.errors.CheckViolation):
        tx.execute("insert into technology (code, family) values ('LASER', 'photons')")


def test_duplicate_coverage(tx: psycopg.Connection[TupleRow]) -> None:
    tx.execute(PROVIDER)
    tx.execute("insert into source (name) values ('test')")
    tx.execute(COVERAGE)
    with pytest.raises(psycopg.errors.UniqueViolation):
        tx.execute(COVERAGE)


def test_address_without_geom(tx: psycopg.Connection[TupleRow]) -> None:
    with pytest.raises(psycopg.errors.NotNullViolation):
        tx.execute("insert into address (street, street_fold, search_key, latin_key) "
                   "values ('ΑΧΑΡΝΩΝ', 'ΑΧΑΡΝΩΝ', 'ΑΧΑΡΝΩΝ', 'AXARNON')")


def test_duplicate_address(tx: psycopg.Connection[TupleRow]) -> None:
    # nulls not distinct, or two postcode-less copies wouldn't collide
    insert = (
        "insert into address (street, street_fold, street_no, locality, geom, search_key, latin_key) "
        "values ('ΑΧΑΡΝΩΝ', 'ΑΧΑΡΝΩΝ', '12', 'ΑΘΗΝΑ', 'SRID=4326;POINT(23.7 37.9)', 'ΑΧΑΡΝΩΝ 12', 'AXARNON 12')"
    )
    tx.execute(insert)
    with pytest.raises(psycopg.errors.UniqueViolation):
        tx.execute(insert)


def test_bad_plan_family(tx: psycopg.Connection[TupleRow]) -> None:
    tx.execute(PROVIDER)
    with pytest.raises(psycopg.errors.CheckViolation):
        tx.execute(
            "insert into plan (provider_id, external_key, name, family) "
            "values ((select id from provider where code = 'X'), 'p', 'P', 'laser')"
        )


def test_bad_hardware(tx: psycopg.Connection[TupleRow]) -> None:
    tx.execute(PROVIDER)
    with pytest.raises(psycopg.errors.CheckViolation):
        tx.execute(
            "insert into plan (provider_id, external_key, name, family, needs_hardware) "
            "values ((select id from provider where code = 'X'), 'p', 'P', 'mobile', 'modem')"
        )


def test_duplicate_price(tx: psycopg.Connection[TupleRow]) -> None:
    plan_id = _plan(tx)
    tx.execute(PRICE, (plan_id, "2026-01-01", 30))
    with pytest.raises(psycopg.errors.UniqueViolation):
        tx.execute(PRICE, (plan_id, "2026-01-01", 31))


def test_bad_cache_source(tx: psycopg.Connection[TupleRow]) -> None:
    tx.execute(PROVIDER)
    address_id = _address(tx)
    with pytest.raises(psycopg.errors.CheckViolation):
        tx.execute(_cache(address_id, source="guess"))


def test_duplicate_answer(tx: psycopg.Connection[TupleRow]) -> None:
    tx.execute(PROVIDER)
    address_id = _address(tx)
    tx.execute(_cache(address_id))
    with pytest.raises(psycopg.errors.UniqueViolation):
        tx.execute(_cache(address_id))


def test_null_serviceable(tx: psycopg.Connection[TupleRow]) -> None:
    tx.execute(PROVIDER)
    address_id = _address(tx)
    with pytest.raises(psycopg.errors.NotNullViolation):
        tx.execute(
            "insert into availability (address_id, provider_id, technology, source, "
            "assertion, observed_at, expires_at) values "
            f"({address_id}, (select id from provider where code = 'X'), 'FTTH', "
            "'register', 'declared', now(), now() + interval '30 days')"
        )


def test_openapi_contract() -> None:
    held = json.loads((Path(__file__).resolve().parent.parent / "schema" / "openapi.json").read_text(encoding="utf-8"))
    loose = copy.deepcopy(held)
    for schema in loose["components"]["schemas"].values():
        for field in schema.get("properties", {}).values():
            field.pop("pattern", None)  # what a newer pydantic does to decimals
            field.pop("description", None)
    assert contract(loose) == contract(held)

    renamed = copy.deepcopy(held)
    fields = renamed["components"]["schemas"]["Health"]["properties"]
    fields["rows"] = fields.pop("addresses")
    assert contract(renamed) != contract(held)

    # a field called title is a field, not a keyword
    assert contract({"properties": {"title": {"type": "string"}}}) == {"properties": {"title": {"type": "string"}}}


def test_openapi() -> None:
    done = subprocess.run([sys.executable, "-m", "tools.openapi_schema", "--check"],
                          cwd=Path(__file__).resolve().parent.parent, capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
