"""Saying whether an operator's checker is working."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from probe.health import BROKEN, DEGRADED, HEALTHY, UNTRIED, Health, state

NOW = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)


def test_answering_every_time_is_healthy() -> None:
    assert state(recent=10, answered=10, last_ok=NOW, now=NOW) == HEALTHY


def test_answering_none_of_the_time_is_broken() -> None:
    assert state(recent=10, answered=0, last_ok=None, now=NOW) == BROKEN


def test_answering_some_of_the_time_is_not_working() -> None:
    """A checker that works one time in three is not working, however many answers arrive."""
    assert state(recent=10, answered=3, last_ok=NOW, now=NOW) == DEGRADED
    assert state(recent=10, answered=9, last_ok=NOW, now=NOW) == HEALTHY


def test_a_quiet_night_is_not_a_failure() -> None:
    """The sweep may simply have had nothing due; a recent answer still counts as evidence."""
    assert state(recent=0, answered=0, last_ok=NOW - timedelta(days=1), now=NOW) == HEALTHY


def test_a_long_silence_is_not_health_either() -> None:
    assert state(recent=0, answered=0, last_ok=NOW - timedelta(days=30), now=NOW) == UNTRIED
    assert state(recent=0, answered=0, last_ok=None, now=NOW) == UNTRIED


def test_the_reader_is_told_a_date_not_a_status() -> None:
    """An operator missing from a comparison is a worse lie than a visible gap."""
    gone = Health("NOVA", BROKEN, datetime(2026, 3, 12, tzinfo=UTC), 6, 0)
    assert gone.says == "has not answered since 12 March"
    assert Health("OTE", HEALTHY, NOW, 6, 6).says == "answering"
    assert Health("X", BROKEN, None, 3, 0).says == "has never answered"
