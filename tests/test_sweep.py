"""Choosing which addresses to ask about again."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import psycopg
import pytest
from psycopg.rows import TupleRow

from probe.adapter import Offer, Probed, Target
from probe.sweep import stale, sweep

NOW = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)
TABLES = "probe_attempt, availability, address, municipality, raw_dimos"


class Fake:
    """An operator that always answers, so the sweep is tested and nobody is asked."""

    code = "OTE"

    def __init__(self) -> None:
        self.asked: list[int] = []

    def check(self, conn: psycopg.Connection[TupleRow], target: Target) -> Probed:
        self.asked.append(target.address_id)
        return Probed(serviceable=True, offers=(Offer(technology="FTTH"),))


@pytest.fixture
def queue(db: psycopg.Connection[TupleRow]) -> Iterator[psycopg.Connection[TupleRow]]:
    db.execute(f"truncate {TABLES} cascade")
    db.execute(
        "insert into municipality (id, name, geom) values (1, 'ΔΗΜΟΣ ΑΘΗΝΑΙΩΝ', "
        "st_setsrid(st_geomfromtext('MULTIPOLYGON(((23 37, 24 37, 24 38, 23 37)))'), 4326))"
    )
    db.commit()
    yield db
    db.execute(f"truncate {TABLES} cascade")
    db.commit()


def place(conn: psycopg.Connection[TupleRow], address_id: int, premises: int | None,
          expires: datetime) -> None:
    conn.execute(
        "insert into address (id, street, street_fold, street_no, municipality_id, premises, "
        "geom, search_key, latin_key) values (%s, 'ΟΔΟΣ', 'ΟΔΟΣ', %s, 1, %s, "
        "st_setsrid(st_point(23.5, 37.5), 4326), 'ΟΔΟΣ', 'ODOS')",
        (address_id, str(address_id), premises),
    )
    conn.execute(
        "insert into availability (address_id, provider_id, technology, serviceable, source, "
        "assertion, observed_at, expires_at) select %s, p.id, 'FTTH', true, 'isp-live', "
        "'declared', %s, %s from provider p where p.code = 'OTE'",
        (address_id, expires - timedelta(days=30), expires),
    )
    conn.commit()


def test_the_most_lived_in_address_is_asked_first(queue: psycopg.Connection[TupleRow]) -> None:
    """Where more people live, more people will ask, so the answer is worth more."""
    place(queue, 1, 4, NOW - timedelta(days=1))
    place(queue, 2, 198, NOW - timedelta(days=1))
    place(queue, 3, 30, NOW - timedelta(days=1))
    assert stale(queue, NOW, 10) == [2, 3, 1]


def test_an_answer_that_has_not_expired_is_left_alone(
    queue: psycopg.Connection[TupleRow],
) -> None:
    place(queue, 1, 10, NOW + timedelta(days=90))
    assert stale(queue, NOW, 10) == []


def test_one_about_to_expire_is_taken_early(queue: psycopg.Connection[TupleRow]) -> None:
    """Refreshing at midnight tomorrow is the same work done later and served staler."""
    place(queue, 1, 10, NOW + timedelta(hours=6))
    assert stale(queue, NOW, 10) == [1]


def test_an_address_with_no_count_is_still_asked_about(
    queue: psycopg.Connection[TupleRow],
) -> None:
    """The register leaves premises null often. Null is unknown, and unknown is not zero."""
    place(queue, 1, None, NOW - timedelta(days=1))
    assert stale(queue, NOW, 10) == [1]


def test_the_budget_is_what_one_run_costs(queue: psycopg.Connection[TupleRow]) -> None:
    for i in range(1, 6):
        place(queue, i, i * 10, NOW - timedelta(days=1))
    assert len(stale(queue, NOW, 2)) == 2


def test_a_refreshed_answer_falls_out_of_the_queue(
    queue: psycopg.Connection[TupleRow],
) -> None:
    """The query is the queue: nothing has to remember where the last run stopped."""
    place(queue, 1, 10, NOW - timedelta(days=1))
    fake = Fake()
    asked, answered = sweep(queue, [fake], NOW, budget=10, pace=0.0)
    assert (asked, answered) == (1, 1)
    assert fake.asked == [1]
    assert stale(queue, NOW, 10) == []
