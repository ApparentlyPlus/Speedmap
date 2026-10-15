from __future__ import annotations

from decimal import Decimal

from ranking.measured import Measured, for_family
from ranking.offer import speed

D = Decimal


def _fixed(mbps: int, tests: int) -> Measured:
    return Measured(family="fixed", down_mbps=D(mbps), up_mbps=D(10), tests=tests)


def _mobile(mbps: int, tests: int) -> Measured:
    return Measured(family="mobile", down_mbps=D(mbps), up_mbps=D(10), tests=tests)


def test_for_family() -> None:
    found = {"fixed": _fixed(100, 50), "mobile": _mobile(200, 50)}
    assert for_family(found, "copper") is found["fixed"]
    assert for_family(found, "fiber") is found["fixed"]
    assert for_family(found, "wireless") is found["mobile"]
    # a dish would drag the fixed median down
    assert for_family(found, "satellite") is None


def test_speed_basis() -> None:
    s = speed("copper", D(100), D(100), D(93), None, _fixed(173, 898))
    assert s.mbps == D(93)
    assert s.basis == "quoted"

    s = speed("copper", D(100), D(100), None, D(30), _fixed(60, 400))
    assert s.basis == "measured"
    assert s.tests == 400
    assert s.confidence > 0.9

    # fiber ignores the median, so it's not "measured"
    s = speed("fiber", D(1000), None, None, None, _fixed(173, 898))
    assert s.mbps == D(1000)
    assert s.basis == "advertised"
    assert s.tests == 0

    s = speed("copper", D(100), D(100), None, None, None)
    assert s.mbps == D(100)
    assert s.basis == "advertised"


def test_speed_tile() -> None:
    strong = speed("wireless", D(1000), None, None, D(300), _mobile(262, 6), D(1000))
    weak = speed("wireless", D(1000), None, None, D(30), _mobile(262, 6), D(100))
    assert strong.mbps is not None and weak.mbps is not None
    assert weak.mbps < strong.mbps
    assert weak.mbps == D(100)

    few = speed("copper", D(100), D(100), None, None, _fixed(60, 6))
    many = speed("copper", D(100), D(100), None, None, _fixed(60, 900))
    assert few.confidence < many.confidence
