"""Asking the operators, and keeping only what is worth keeping."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import psycopg
import pytest
from psycopg.rows import TupleRow

from probe.adapter import Offer, Probed
from probe.run import Asked, best, due, store
from probe.ttl import CHANGING, SETTLED, VOLATILE

NOW = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)
TABLES = "probe_attempt, availability, address, raw_coverpoint, municipality, raw_dimos"


@pytest.fixture
def asked(db: psycopg.Connection[TupleRow]) -> Iterator[psycopg.Connection[TupleRow]]:
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


def probed(*offers: Offer, serviceable: bool = True, conclusive: bool = True) -> Probed:
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
    assert best(probed(offer("ADSL", 24), offer("FTTH", 1000))) == Decimal(1000)
    assert best(probed(offer("FWA", None))) is None
    assert best(probed()) is None


def test_an_answer_is_kept_for_as_long_as_it_is_worth(
    asked: psycopg.Connection[TupleRow],
) -> None:
    written = store(asked, 1, Asked("OTE", probed(offer("FTTH", 1000))), NOW)
    assert written == 1
    row = asked.execute("select expires_at - observed_at from availability").fetchone()
    assert row == (SETTLED,)


def test_a_slow_answer_is_asked_again_sooner(asked: psycopg.Connection[TupleRow]) -> None:
    store(asked, 1, Asked("OTE", probed(offer("VDSL", 50))), NOW)
    row = asked.execute("select expires_at - observed_at from availability").fetchone()
    assert row == (VOLATILE,)

    store(asked, 1, Asked("VODAFONE", probed(offer("VECT_VDSL", 100))), NOW)
    row = asked.execute(
        "select expires_at - observed_at from availability v join provider p "
        "on p.id = v.provider_id where p.code = 'VODAFONE'"
    ).fetchone()
    assert row == (CHANGING,)


def test_a_failure_is_recorded_as_a_failure_and_nothing_else(
    asked: psycopg.Connection[TupleRow],
) -> None:
    """A checker that could not be reached has not said an address is unserved."""
    assert store(asked, 1, Asked("OTE", None, error="timed out"), NOW) == 0
    assert rows(asked, "availability") == 0
    row = asked.execute("select ok, serviceable, detail from probe_attempt").fetchone()
    assert row == (False, None, "timed out")


def test_an_address_we_cannot_spell_is_not_the_operator_failing(
    asked: psycopg.Connection[TupleRow],
) -> None:
    """Recorded, and not counted against them. See migration 0057.

    Both adapters that want an address in words want their own spelling of it, and we hold
    that for 43% of streets — Πατησίων is not among them. An adapter handed one of the rest
    reports that it cannot look it up, which is the only correct thing it can do, and was
    being stored identically to a checker that had broken. Nova spent ten days reading as
    "has not answered" on the strength of eleven such attempts and no real failure at all.
    """
    gap = Asked("NOVA", None, error="no spelling recorded for ΠΑΤΗΣΙΩΝ", askable=False)
    assert store(asked, 1, gap, NOW) == 0
    row = asked.execute("select ok, askable, detail from probe_attempt").fetchone()
    assert row == (False, False, "no spelling recorded for ΠΑΤΗΣΙΩΝ")


def test_a_real_failure_is_still_theirs(asked: psycopg.Connection[TupleRow]) -> None:
    """The default stays askable, so nothing that was counted before stops being counted."""
    assert store(asked, 1, Asked("VODAFONE", None, error="qualification returned 500"), NOW) == 0
    assert asked.execute("select ok, askable from probe_attempt").fetchone() == (False, True)


def test_being_told_to_investigate_is_not_an_answer_either(
    asked: psycopg.Connection[TupleRow],
) -> None:
    assert store(asked, 1, Asked("OTE", probed(conclusive=False, serviceable=False)), NOW) == 0
    assert rows(asked, "availability") == 0
    assert asked.execute("select ok from probe_attempt").fetchone() == (False,)


def test_an_explicit_refusal_is_an_answer_but_not_an_offer(
    asked: psycopg.Connection[TupleRow],
) -> None:
    """They were asked and said no, which is worth recording and is not a row of coverage."""
    assert store(asked, 1, Asked("NOVA", probed(serviceable=False)), NOW) == 0
    assert rows(asked, "availability") == 0
    assert asked.execute("select ok, serviceable from probe_attempt").fetchone() == (True, False)


def test_a_broken_checker_is_left_alone_for_a_few_hours(
    asked: psycopg.Connection[TupleRow],
) -> None:
    """Asking it on every request is how a rate limit becomes a ban."""
    store(asked, 1, Asked("OTE", None, error="503"), NOW)
    asked.commit()
    assert due(asked, 1, "OTE", NOW + timedelta(hours=1)) is False
    assert due(asked, 1, "OTE", NOW + timedelta(hours=7)) is True


def test_an_operator_that_answered_may_be_asked_again(
    asked: psycopg.Connection[TupleRow],
) -> None:
    """The backoff is for failure. A real answer is governed by its own lifetime."""
    store(asked, 1, Asked("OTE", probed(offer("FTTH", 1000))), NOW)
    asked.commit()
    assert due(asked, 1, "OTE", NOW + timedelta(minutes=1)) is True


def test_an_operator_never_asked_is_due(asked: psycopg.Connection[TupleRow]) -> None:
    assert due(asked, 1, "OTE", NOW) is True


def test_a_refusal_is_remembered_for_a_month(asked: psycopg.Connection[TupleRow]) -> None:
    """It leaves no row in availability to expire, so nothing else would ever stop us
    asking again on every visit to the address."""
    store(asked, 1, Asked("NOVA", probed(serviceable=False)), NOW)
    asked.commit()
    assert due(asked, 1, "NOVA", NOW + timedelta(days=7)) is False
    assert due(asked, 1, "NOVA", NOW + timedelta(days=31)) is True
