"""
Data invariants, each with a control that proves the query actually fires.

An invariant that only ever runs against clean data is indistinguishable from one
that is broken, so every .sql file must appear in CONTROLS.
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

CONTROLS: dict[str, tuple[str, ...]] = {
    "coverage_family_matches_technology": (MISLABELLED_COVERAGE.format(table="coverage"),),
    "coverage_area_family_matches_technology": (
        MISLABELLED_COVERAGE.format(table="coverage_area"),
    ),
    "availability_expires_after_observed": (FOLDED_ADDRESS, EXPIRED_BEFORE_OBSERVED),
    "address_search_key_is_folded": (UNFOLDED_ADDRESS,),
    "street_best_is_the_best_operator": (DISAGREEING_STREET,),
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
