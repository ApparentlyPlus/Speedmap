from __future__ import annotations

from datetime import UTC, datetime, timedelta

from probe.health import BROKEN, DEGRADED, HEALTHY, UNTRIED, Health, state

NOW = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)


def test_state() -> None:
    assert state(recent=10, answered=10, last_ok=NOW, now=NOW) == HEALTHY
    assert state(recent=10, answered=0, last_ok=None, now=NOW) == BROKEN
    assert state(recent=10, answered=3, last_ok=NOW, now=NOW) == DEGRADED
    assert state(recent=10, answered=9, last_ok=NOW, now=NOW) == HEALTHY

    # quiet night, the sweep had nothing due
    assert state(recent=0, answered=0, last_ok=NOW - timedelta(days=1), now=NOW) == HEALTHY
    assert state(recent=0, answered=0, last_ok=NOW - timedelta(days=30), now=NOW) == UNTRIED
    assert state(recent=0, answered=0, last_ok=None, now=NOW) == UNTRIED


def test_says() -> None:
    gone = Health("NOVA", BROKEN, datetime(2026, 3, 12, tzinfo=UTC), 6, 0)
    assert gone.says == "has not answered since 12 March"
    assert Health("TELEKOM", HEALTHY, NOW, 6, 6).says == "answering"
    assert Health("X", BROKEN, None, 3, 0).says == "has never answered"

    # Nova showed "not asked yet" after answering four times
    assert Health("NOVA", UNTRIED, datetime(2026, 9, 10, tzinfo=UTC), 0, 0).says == "last answered 10 September"
    assert Health("NEW", UNTRIED, None, 0, 0).says == "not asked yet"

    flaky = Health("VODAFONE", DEGRADED, NOW, 12, 10)
    assert flaky.says == "answering 10 times in 12"
    assert "has not answered" not in flaky.says
