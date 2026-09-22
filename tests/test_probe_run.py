"""Asking the operators, and keeping only what is worth keeping."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import psycopg
import pytest
from psycopg.rows import TupleRow

from probe.adapter import Offer, Probed
from probe.run import Reply, best, due, store
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


def result(*offers: Offer, serviceable: bool = True, conclusive: bool = True) -> Probed:
    return Probed(serviceable=serviceable, offers=offers, conclusive=conclusive)


def offer(technology: str, mbps: int | None) -> Offer:
    return Offer(technology=technology,
                 max_down_mbps=None if mbps is None else Decimal(mbps))


def rows(conn: psycopg.Connection[TupleRow], table: str) -> int:
    found = conn.execute(f"select count(*) from {table}").fetchone()
    assert found is not None
    return int(found[0])


def test_the_fastest_offer_sets_the_lifetime() -> None:
    """A gigabit among the offers makes the whole answer a settled one."""
    assert best(result(offer("ADSL", 24), offer("FTTH", 1000))) == Decimal(1000)
    assert best(result(offer("FWA", None))) is None
    assert best(result()) is None


def test_an_answer_is_kept_for_as_long_as_it_is_worth(
    reply: psycopg.Connection[TupleRow],
) -> None:
    written = store(reply, 1, Reply("TELEKOM", result(offer("FTTH", 1000))), NOW)
    assert written == 1
    row = reply.execute("select expires_at - observed_at from availability").fetchone()
    assert row == (SETTLED,)


def test_a_slow_answer_is_asked_again_sooner(reply: psycopg.Connection[TupleRow]) -> None:
    store(reply, 1, Reply("TELEKOM", result(offer("VDSL", 50))), NOW)
    row = reply.execute("select expires_at - observed_at from availability").fetchone()
    assert row == (VOLATILE,)

    store(reply, 1, Reply("VODAFONE", result(offer("VECT_VDSL", 100))), NOW)
    row = reply.execute(
        "select expires_at - observed_at from availability v join provider p "
        "on p.id = v.provider_id where p.code = 'VODAFONE'"
    ).fetchone()
    assert row == (CHANGING,)


def test_a_failure_is_recorded_as_a_failure_and_nothing_else(
    reply: psycopg.Connection[TupleRow],
) -> None:
    """A checker that could not be reached has not said an address is unserved."""
    assert store(reply, 1, Reply("TELEKOM", None, error="timed out"), NOW) == 0
    assert rows(reply, "availability") == 0
    row = reply.execute("select ok, serviceable, detail from probe_attempt").fetchone()
    assert row == (False, None, "timed out")


def test_an_address_we_cannot_spell_is_not_the_operator_failing(
    reply: psycopg.Connection[TupleRow],
) -> None:
    """Recorded, and not counted against them. See migration 0057.

    Both adapters that want an address in words want their own spelling of it, and we hold
    that for 43% of streets, Πατησίων is not among them.
    """
    gap = Reply("NOVA", None, error="no spelling recorded for ΠΑΤΗΣΙΩΝ", askable=False)
    assert store(reply, 1, gap, NOW) == 0
    row = reply.execute("select ok, askable, detail from probe_attempt").fetchone()
    assert row == (False, False, "no spelling recorded for ΠΑΤΗΣΙΩΝ")


def test_a_real_failure_is_still_theirs(reply: psycopg.Connection[TupleRow]) -> None:
    """The default stays askable, so nothing that was counted before stops being counted."""
    assert store(reply, 1, Reply("VODAFONE", None, error="qualification returned 500"), NOW) == 0
    assert reply.execute("select ok, askable from probe_attempt").fetchone() == (False, True)


def test_being_told_to_investigate_is_not_an_answer_either(
    reply: psycopg.Connection[TupleRow],
) -> None:
    assert store(reply, 1, Reply("TELEKOM", result(conclusive=False, serviceable=False)), NOW) == 0
    assert rows(reply, "availability") == 0
    assert reply.execute("select ok from probe_attempt").fetchone() == (False,)


def test_an_explicit_refusal_is_an_answer_but_not_an_offer(
    reply: psycopg.Connection[TupleRow],
) -> None:
    """They were asked and said no, which is worth recording and is not a row of coverage."""
    assert store(reply, 1, Reply("NOVA", result(serviceable=False)), NOW) == 0
    assert rows(reply, "availability") == 0
    assert reply.execute("select ok, serviceable from probe_attempt").fetchone() == (True, False)


def test_a_broken_checker_is_left_alone_for_a_few_hours(
    reply: psycopg.Connection[TupleRow],
) -> None:
    """Asking it on every request is how a rate limit becomes a ban."""
    store(reply, 1, Reply("TELEKOM", None, error="503"), NOW)
    reply.commit()
    assert due(reply, 1, "TELEKOM", NOW + timedelta(hours=1)) is False
    assert due(reply, 1, "TELEKOM", NOW + timedelta(hours=7)) is True


def test_an_operator_that_answered_may_be_asked_again(
    reply: psycopg.Connection[TupleRow],
) -> None:
    """The backoff is for failure. A real answer is governed by its own lifetime."""
    store(reply, 1, Reply("TELEKOM", result(offer("FTTH", 1000))), NOW)
    reply.commit()
    assert due(reply, 1, "TELEKOM", NOW + timedelta(minutes=1)) is True


def test_an_operator_never_asked_is_due(reply: psycopg.Connection[TupleRow]) -> None:
    assert due(reply, 1, "TELEKOM", NOW) is True


def test_a_refusal_is_remembered_for_a_month(reply: psycopg.Connection[TupleRow]) -> None:
    """It leaves no row in availability to expire, so nothing else would ever stop us
    asking again on every visit to the address."""
    store(reply, 1, Reply("NOVA", result(serviceable=False)), NOW)
    reply.commit()
    assert due(reply, 1, "NOVA", NOW + timedelta(days=7)) is False
    assert due(reply, 1, "NOVA", NOW + timedelta(days=31)) is True
