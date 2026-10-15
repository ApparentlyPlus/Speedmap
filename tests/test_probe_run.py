from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import psycopg
import pytest
from psycopg.rows import TupleRow

from probe.adapter import Offer, Probed
from probe.health import BLOCKED, health
from probe.run import LONGEST_REST, PER_MINUTE, REST, Reply, best, crowded, due, resting, store
from probe.ttl import CHANGING, SETTLED, VOLATILE

NOW = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)
TABLES = "probe_attempt, availability, address, raw_coverpoint, municipality, raw_dimos"


@pytest.fixture
def reply(db: psycopg.Connection[TupleRow]) -> Iterator[psycopg.Connection[TupleRow]]:
    db.execute(f"truncate {TABLES} cascade")
    db.execute(
        "insert into municipality (id, name, geom) values (1, 'ΔΗΜΟΣ ΑΘΗΝΑΙΩΝ', "
        "st_setsrid(st_geomfromtext('MULTIPOLYGON(((23 37, 24 37, 24 38, 23 37)))'), 4326))"
    )
    db.execute(
        "insert into address (id, street, street_fold, street_no, municipality_id, geom, "
        "search_key, latin_key) values (1, 'ΟΔΟΣ', 'ΟΔΟΣ', '1', 1, "
        "st_setsrid(st_point(23.5, 37.5), 4326), 'ΟΔΟΣ', 'ODOS')"
    )
    db.commit()
    yield db
    db.execute(f"truncate {TABLES} cascade")
    db.commit()


def _result(*offers: Offer, serviceable: bool = True, conclusive: bool = True) -> Probed:
    return Probed(serviceable=serviceable, offers=offers, conclusive=conclusive)


def _offer(technology: str, mbps: int | None) -> Offer:
    return Offer(technology=technology, max_down_mbps=None if mbps is None else Decimal(mbps))


def _count(conn: psycopg.Connection[TupleRow], table: str) -> int:
    found = conn.execute(f"select count(*) from {table}").fetchone()
    assert found is not None
    return int(found[0])


def _clear(conn: psycopg.Connection[TupleRow]) -> None:
    conn.execute("truncate probe_attempt, availability")
    conn.commit()


def _blocked(conn: psycopg.Connection[TupleRow], at: datetime, wall: str | None = "Imperva") -> None:
    store(conn, 1, Reply("TELEKOM", None, error="blocked", blocked=wall), at)


GIGABIT = Reply("TELEKOM", _result(_offer("FTTH", 1000)))


def test_best() -> None:
    assert best(_result(_offer("ADSL", 24), _offer("FTTH", 1000))) == Decimal(1000)
    assert best(_result(_offer("FWA", None))) is None
    assert best(_result()) is None


def test_store_ttl(reply: psycopg.Connection[TupleRow]) -> None:
    assert store(reply, 1, GIGABIT, NOW) == 1
    assert reply.execute("select expires_at - observed_at from availability").fetchone() == (SETTLED,)

    _clear(reply)
    store(reply, 1, Reply("TELEKOM", _result(_offer("VDSL", 50))), NOW)
    assert reply.execute("select expires_at - observed_at from availability").fetchone() == (VOLATILE,)

    store(reply, 1, Reply("VODAFONE", _result(_offer("VECT_VDSL", 100))), NOW)
    row = reply.execute(
        "select expires_at - observed_at from availability v join provider p "
        "on p.id = v.provider_id where p.code = 'VODAFONE'"
    ).fetchone()
    assert row == (CHANGING,)


def test_store_failed(reply: psycopg.Connection[TupleRow]) -> None:
    # unreachable isn't unserved
    assert store(reply, 1, Reply("TELEKOM", None, error="timed out"), NOW) == 0
    assert _count(reply, "availability") == 0
    assert reply.execute("select ok, serviceable, detail from probe_attempt").fetchone() == (False, None, "timed out")

    # our gap, not theirs (migration 0057). We hold their spelling for 43% of streets
    _clear(reply)
    gap = Reply("NOVA", None, error="no spelling recorded for ΠΑΤΗΣΙΩΝ", askable=False)
    assert store(reply, 1, gap, NOW) == 0
    row = reply.execute("select ok, askable, detail from probe_attempt").fetchone()
    assert row == (False, False, "no spelling recorded for ΠΑΤΗΣΙΩΝ")

    _clear(reply)
    assert store(reply, 1, Reply("VODAFONE", None, error="qualification returned 500"), NOW) == 0
    assert reply.execute("select ok, askable from probe_attempt").fetchone() == (False, True)

    _clear(reply)
    assert store(reply, 1, Reply("TELEKOM", _result(conclusive=False, serviceable=False)), NOW) == 0
    assert _count(reply, "availability") == 0
    assert reply.execute("select ok from probe_attempt").fetchone() == (False,)

    # a no is an answer, but not a coverage row
    _clear(reply)
    assert store(reply, 1, Reply("NOVA", _result(serviceable=False)), NOW) == 0
    assert _count(reply, "availability") == 0
    assert reply.execute("select ok, serviceable from probe_attempt").fetchone() == (True, False)


def test_due(reply: psycopg.Connection[TupleRow]) -> None:
    assert due(reply, 1, "TELEKOM", NOW) is True

    store(reply, 1, Reply("TELEKOM", None, error="503"), NOW)
    reply.commit()
    assert due(reply, 1, "TELEKOM", NOW + timedelta(hours=1)) is False
    assert due(reply, 1, "TELEKOM", NOW + timedelta(hours=7)) is True

    _clear(reply)
    store(reply, 1, GIGABIT, NOW)
    reply.commit()
    assert due(reply, 1, "TELEKOM", NOW + timedelta(minutes=1)) is True

    # a no leaves nothing in availability to expire
    store(reply, 1, Reply("NOVA", _result(serviceable=False)), NOW)
    reply.commit()
    assert due(reply, 1, "NOVA", NOW + timedelta(days=7)) is False
    assert due(reply, 1, "NOVA", NOW + timedelta(days=31)) is True


def test_resting(reply: psycopg.Connection[TupleRow]) -> None:
    _blocked(reply, NOW)
    assert resting(reply, "TELEKOM", NOW + timedelta(minutes=10)) == NOW + REST
    assert resting(reply, "TELEKOM", NOW + REST + timedelta(seconds=1)) is None

    _clear(reply)
    for i in range(3):
        _blocked(reply, NOW + timedelta(hours=i))
    last = NOW + timedelta(hours=2)
    assert resting(reply, "TELEKOM", last) == last + REST * 4

    _clear(reply)
    for i in range(8):
        _blocked(reply, NOW + timedelta(days=i))
    last = NOW + timedelta(days=7)
    assert resting(reply, "TELEKOM", last) == last + LONGEST_REST

    _clear(reply)
    _blocked(reply, NOW)
    store(reply, 1, GIGABIT, NOW + timedelta(minutes=1))
    assert resting(reply, "TELEKOM", NOW + timedelta(minutes=2)) is None

    _clear(reply)
    _blocked(reply, NOW, "Cloudflare")
    assert reply.execute("select ok, blocked from probe_attempt").fetchone() == (False, "Cloudflare")


def test_crowded(reply: psycopg.Connection[TupleRow]) -> None:
    for i in range(PER_MINUTE):
        store(reply, 1, Reply("TELEKOM", None, error="timeout"), NOW - timedelta(seconds=i))
    assert crowded(reply, "TELEKOM", NOW)
    assert not crowded(reply, "TELEKOM", NOW + timedelta(minutes=2))


def test_block_alerts(reply: psycopg.Connection[TupleRow], monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[str] = []
    monkeypatch.setattr("probe.run.alert_later", lambda title, message, urgent=False: sent.append(title))
    _blocked(reply, NOW)
    _blocked(reply, NOW + timedelta(hours=1))
    store(reply, 1, GIGABIT, NOW + timedelta(hours=2))
    store(reply, 1, GIGABIT, NOW + timedelta(hours=3))
    assert sent == ["TELEKOM is blocking us", "TELEKOM is answering again"]


def test_block_health(reply: psycopg.Connection[TupleRow]) -> None:
    _blocked(reply, NOW)
    states = health(reply, ["TELEKOM"], NOW + timedelta(minutes=5))
    assert states["TELEKOM"].state == BLOCKED
    assert states["TELEKOM"].says == "blocked by Imperva, asked again after 12:30 UTC"
