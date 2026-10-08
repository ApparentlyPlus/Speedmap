"""How often one caller may ask."""

from __future__ import annotations

from api.throttle import PROBE, READ, REPORT, SEARCH, Throttle, limit_for


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_each_request_is_held_to_its_own_limit() -> None:
    assert limit_for("POST", "/addresses/7/probe") is PROBE
    assert limit_for("POST", "/reports") is REPORT
    assert limit_for("GET", "/search") is SEARCH
    assert limit_for("GET", "/addresses/7/options") is READ


def test_a_caller_past_the_limit_waits_and_then_may_ask_again() -> None:
    clock = Clock()
    throttle = Throttle(clock)
    for _ in range(PROBE.times):
        assert throttle.wait("203.0.113.7", PROBE) == 0
    held = throttle.wait("203.0.113.7", PROBE)
    assert 0 < held <= PROBE.per_s + 1
    clock.now += PROBE.per_s + 1
    assert throttle.wait("203.0.113.7", PROBE) == 0


def test_one_caller_never_spends_anothers_limit() -> None:
    throttle = Throttle(Clock())
    for _ in range(REPORT.times):
        throttle.wait("203.0.113.7", REPORT)
    assert throttle.wait("203.0.113.7", REPORT) > 0
    assert throttle.wait("198.51.100.2", REPORT) == 0


def test_callers_long_gone_are_forgotten() -> None:
    clock = Clock()
    throttle = Throttle(clock)
    throttle.wait("203.0.113.7", READ)
    clock.now += 4000
    throttle.sweep(clock.now)
    assert throttle.seen == {}
