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
DAY = timedelta(days=1)


class Fake:
    code = "TELEKOM"

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


def _place(conn: psycopg.Connection[TupleRow], address_id: int, premises: int | None, expires: datetime) -> None:
    conn.execute(
        "insert into address (id, street, street_fold, street_no, municipality_id, premises, "
        "geom, search_key, latin_key) values (%s, 'ΟΔΟΣ', 'ΟΔΟΣ', %s, 1, %s, "
        "st_setsrid(st_point(23.5, 37.5), 4326), 'ΟΔΟΣ', 'ODOS')",
        (address_id, str(address_id), premises),
    )
    conn.execute(
        "insert into availability (address_id, provider_id, technology, serviceable, source, "
        "assertion, observed_at, expires_at) select %s, p.id, 'FTTH', true, 'isp-live', "
        "'declared', %s, %s from provider p where p.code = 'TELEKOM'",
        (address_id, expires - timedelta(days=30), expires),
    )
    conn.commit()


def _clear(conn: psycopg.Connection[TupleRow]) -> None:
    conn.execute("truncate probe_attempt, availability, address cascade")
    conn.commit()


def test_stale(queue: psycopg.Connection[TupleRow]) -> None:
    # most premises first
    _place(queue, 1, 4, NOW - DAY)
    _place(queue, 2, 198, NOW - DAY)
    _place(queue, 3, 30, NOW - DAY)
    assert stale(queue, NOW, 10) == [2, 3, 1]

    _clear(queue)
    _place(queue, 1, 10, NOW + timedelta(days=90))
    assert stale(queue, NOW, 10) == []

    _clear(queue)
    _place(queue, 1, 10, NOW + timedelta(hours=6))
    assert stale(queue, NOW, 10) == [1]

    # premises is often null, which isn't zero
    _clear(queue)
    _place(queue, 1, None, NOW - DAY)
    assert stale(queue, NOW, 10) == [1]

    _clear(queue)
    for i in range(1, 6):
        _place(queue, i, i * 10, NOW - DAY)
    assert len(stale(queue, NOW, 2)) == 2


def test_stale_rest(queue: psycopg.Connection[TupleRow]) -> None:
    _place(queue, 1, 500, NOW - DAY)
    _place(queue, 2, 5, NOW - DAY)
    queue.execute(
        "insert into probe_attempt (address_id, provider_id, attempted_at, ok, askable) "
        "select 1, p.id, %s, false, true from provider p where p.code = 'TELEKOM'",
        (NOW - timedelta(days=2),),
    )
    queue.commit()
    assert stale(queue, NOW, 10) == [2]
    assert stale(queue, NOW + timedelta(days=6), 10) == [1, 2]


def test_sweep(queue: psycopg.Connection[TupleRow]) -> None:
    _place(queue, 1, 10, NOW - DAY)
    fake = Fake()
    asked, answered = sweep(queue, [fake], NOW, budget=10, pace=0.0)
    assert (asked, answered) == (1, 1)
    assert fake.asked == [1]
    assert stale(queue, NOW, 10) == []
