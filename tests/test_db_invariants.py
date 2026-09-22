"""Data invariants, each with a control that proves the query actually fires.
"""

from __future__ import annotations

from pathlib import Path

import psycopg
import pytest
from psycopg.rows import TupleRow

INVARIANTS = {p.stem: p for p in sorted((Path(__file__).parent / "invariants").glob("*.sql"))}

FOLDED_ADDRESS = (
    "insert into address (street, street_fold, geom, search_key, latin_key) "
    "values ('ΑΧΑΡΝΩΝ', 'ΑΧΑΡΝΩΝ', 'SRID=4326;POINT(23.7 37.9)', 'ΑΧΑΡΝΩΝ', 'AXARNON')"
)

UNFOLDED_ADDRESS = (
    "insert into address (street, street_fold, geom, search_key, latin_key) "
    "values ('Αχαρνών', 'ΑΧΑΡΝΩΝ', 'SRID=4326;POINT(23.7 37.9)', 'αχαρνών', 'AXARNON')"
)

MISLABELLED_COVERAGE = (
    "insert into {table} (source, source_ref, provider_id, technology, family, assertion) "
    "values ('test', 'x', (select id from provider where code = 'TEST'), "
    "'FTTH', 'copper', 'declared')"
)

EXPIRED_BEFORE_OBSERVED = (
    "insert into availability (address_id, provider_id, technology, serviceable, "
    "source, assertion, observed_at, expires_at) values "
    "((select id from address limit 1), (select id from provider where code = 'TEST'), "
    "'FTTH', true, 'register', 'declared', now(), now() - interval '1 day')"
)

# A street whose overall best disagrees with every operator filed on it.
DISAGREEING_STREET = (
    "insert into street (name, name_fold, latin_key, sort_key, highway, ways, geom, "
    "best_mbps) values ('ΤΕΣΤ', 'ΤΕΣΤ', 'TEST', 'ΤΕΣΤ', 'residential', 1, "
    "'SRID=4326;MULTILINESTRING((23.0 40.7, 23.01 40.71))', 999)"
)

# A street whose only coverage is mobile, and whose figure was taken from it anyway.
MOBILE_STREET = (
    "insert into street (name, name_fold, latin_key, sort_key, highway, ways, geom, "
    "best_mbps) values ('ΚΙΝΗΤΟ', 'ΚΙΝΗΤΟ', 'KINITO', 'ΚΙΝΗΤΟ', 'residential', 1, "
    "'SRID=4326;MULTILINESTRING((23.0 40.7, 23.01 40.71))', 1000)"
)

MOBILE_ADDRESS = (
    "insert into address (street, street_fold, geom, search_key, latin_key) "
    "values ('ΚΙΝΗΤΟ', 'ΚΙΝΗΤΟ', 'SRID=4326;POINT(23.0 40.7)', 'ΚΙΝΗΤΟ', 'KINITO')"
)

MOBILE_COVERAGE = (
    "insert into address_coverage (address_id, provider_id, technology, family, "
    "matched_by, speed_band_id) select a.id, "
    "(select id from provider where code = 'TEST'), 'FWA_5G', 'wireless', 'cell', "
    "(select id from speed_band where min_mbps = 300) from address a "
    "where a.street_fold = 'ΚΙΝΗΤΟ'"
)

# A builder who has passed a door the register locates, and no coverage anywhere.
UNBUILT_BUILDER = (
    "update provider set builds_own_network = true, register_id = 901 where code = 'TEST'",
    "insert into raw_coverpoint (coverid, infrprov, prempass) values ('c1', 901, 12)",
    "insert into address (street, street_fold, geom, search_key, latin_key) "
    "values ('ΤΕΣΤ', 'ΤΕΣΤ', 'SRID=4326;POINT(23.7 37.9)', 'ΤΕΣΤ', 'TEST')",
    "insert into address_point (address_id, coverid) "
    "select id, 'c1' from address where street_fold = 'ΤΕΣΤ'",
)

# An alias that reached a derived table under its own id instead of the company's.
UNRESOLVED_ALIAS = (
    "insert into provider (code, display_name, kind, credited_to) "
    "values ('TEST_ALIAS', 'Test Alias', 'altnet', "
    "(select id from provider where code = 'TEST'))",
    "insert into coverage (source, source_ref, provider_id, technology, family, assertion) "
    "values ('test', 'a', (select id from provider where code = 'TEST_ALIAS'), "
    "'FTTH', 'fiber', 'declared')",
)

# 1,001 filings stacked on one address, which is the shape the register's street-less
# filings collapse into.
PILED_COVERPOINTS = (
    "update provider set builds_own_network = true, register_id = 902 where code = 'TEST'",
    "insert into address (street, street_fold, geom, search_key, latin_key) "
    "values ('ΣΩΡΟΣ', 'ΣΩΡΟΣ', 'SRID=4326;POINT(23.7 37.9)', 'ΣΩΡΟΣ', 'SOROS')",
    "insert into raw_coverpoint (coverid, infrprov, prempass) "
    "select 'pile-' || g, 902, 4 from generate_series(1, 1001) g",
    "insert into address_point (address_id, coverid) "
    "select (select id from address where street_fold = 'ΣΩΡΟΣ'), 'pile-' || g "
    "from generate_series(1, 1001) g",
)

CONTROLS: dict[str, tuple[str, ...]] = {
    "coverpoints_do_not_pile_onto_one_address": PILED_COVERPOINTS,
    "every_builder_reaches_somewhere": UNBUILT_BUILDER,
    "aliases_never_reach_derived_tables": UNRESOLVED_ALIAS,
    "coverage_family_matches_technology": (MISLABELLED_COVERAGE.format(table="coverage"),),
    "coverage_area_family_matches_technology": (
        MISLABELLED_COVERAGE.format(table="coverage_area"),
    ),
    "availability_expires_after_observed": (FOLDED_ADDRESS, EXPIRED_BEFORE_OBSERVED),
    "address_search_key_is_folded": (UNFOLDED_ADDRESS,),
    "street_best_is_the_best_operator": (DISAGREEING_STREET,),
    "street_speed_leaves_mobile_out": (MOBILE_STREET, MOBILE_ADDRESS, MOBILE_COVERAGE),
}


def run(conn: psycopg.Connection[TupleRow], name: str) -> list[TupleRow]:
    return conn.execute(INVARIANTS[name].read_text(encoding="utf-8")).fetchall()


def test_every_invariant_has_a_control() -> None:
    assert set(CONTROLS) == set(INVARIANTS)


@pytest.mark.parametrize("name", sorted(INVARIANTS), ids=str)
def test_invariant_holds(db: psycopg.Connection[TupleRow], name: str) -> None:
    assert run(db, name) == []


@pytest.mark.parametrize("name", sorted(CONTROLS), ids=str)
def test_invariant_detects_its_violation(seeded: psycopg.Connection[TupleRow], name: str) -> None:
    for statement in CONTROLS[name]:
        seeded.execute(statement)
    assert run(seeded, name) != []
