"""Using what people measured, and saying so only when it was used."""

from __future__ import annotations

from decimal import Decimal

from ranking.measured import Measured, for_family
from ranking.offer import speed


def fixed_at(mbps: int, tests: int) -> Measured:
    return Measured(family="fixed", down_mbps=Decimal(mbps), up_mbps=Decimal(10), tests=tests)


def mobile_at(mbps: int, tests: int) -> Measured:
    return Measured(family="mobile", down_mbps=Decimal(mbps), up_mbps=Decimal(10), tests=tests)


def test_a_technology_is_matched_to_one_of_their_two_worlds() -> None:
    """Satellite is in neither: folding a dish into the fixed median drags it down."""
    found = {"fixed": fixed_at(100, 50), "mobile": mobile_at(200, 50)}
    assert for_family(found, "copper") is found["fixed"]
    assert for_family(found, "fiber") is found["fixed"]
    assert for_family(found, "wireless") is found["mobile"]
    assert for_family(found, "satellite") is None


def test_an_operator_quote_beats_everything_measured_nearby() -> None:
    """They are describing this line. A tile is describing the street."""
    got = speed("copper", Decimal(100), Decimal(100), Decimal(93), None, fixed_at(173, 898))
    assert got.mbps == Decimal(93)
    assert got.basis == "quoted"


def test_a_measurement_beats_a_filed_band() -> None:
    got = speed("copper", Decimal(100), Decimal(100), None, Decimal(30), fixed_at(60, 400))
    assert got.basis == "measured"
    assert got.tests == 400
    assert got.confidence > 0.9


def test_fiber_does_not_claim_to_be_measured() -> None:
    """It delivers what it says, so the median is ignored, so calling it measured is a lie."""
    got = speed("fiber", Decimal(1000), None, None, None, fixed_at(173, 898))
    assert got.mbps == Decimal(1000)
    assert got.basis == "advertised"
    assert got.tests == 0


def test_a_tile_is_every_operator_in_it_at_once() -> None:
    """One operator filing a slower band here is saying its own mast is worse, and it knows."""
    strong = speed("wireless", Decimal(1000), None, None, Decimal(300), mobile_at(262, 6),
                   Decimal(1000))
    weak = speed("wireless", Decimal(1000), None, None, Decimal(30), mobile_at(262, 6),
                 Decimal(100))
    assert strong.mbps is not None and weak.mbps is not None
    assert weak.mbps < strong.mbps
    assert weak.mbps == Decimal(100)


def test_confidence_grows_with_the_tests_behind_it() -> None:
    """Six tests in a village and nine hundred in a city are not the same claim."""
    few = speed("copper", Decimal(100), Decimal(100), None, None, fixed_at(60, 6))
    many = speed("copper", Decimal(100), Decimal(100), None, None, fixed_at(60, 900))
    assert few.confidence < many.confidence


def test_with_nothing_at_all_the_advertised_figure_stands() -> None:
    got = speed("copper", Decimal(100), Decimal(100), None, None, None)
    assert got.mbps == Decimal(100)
    assert got.basis == "advertised"
