from __future__ import annotations

from api.throttle import PROBE, READ, REPORT, SEARCH, Throttle, limit_for

IP = "203.0.113.7"


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_limit_for() -> None:
    assert limit_for("POST", "/addresses/7/probe") is PROBE
    assert limit_for("POST", "/reports") is REPORT
    assert limit_for("GET", "/search") is SEARCH
    assert limit_for("GET", "/addresses/7/options") is READ


def test_throttle() -> None:
    clock = Clock()
    t = Throttle(clock)
    for _ in range(PROBE.times):
        assert t.wait(IP, PROBE) == 0
    held = t.wait(IP, PROBE)
    assert 0 < held <= PROBE.per_s + 1
    clock.now += PROBE.per_s + 1
    assert t.wait(IP, PROBE) == 0

    for _ in range(REPORT.times):
        t.wait(IP, REPORT)
    assert t.wait(IP, REPORT) > 0
    assert t.wait("198.51.100.2", REPORT) == 0

    clock.now += 4000
    t.sweep(clock.now)
    assert t.seen == {}
