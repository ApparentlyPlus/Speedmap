"""Expected speed: clamping impossible filings and tempering with measurement."""

from __future__ import annotations

from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from ranking.speed import (
    FULL_CONFIDENCE_TESTS,
    MIN_CONFIDENCE,
    clamp,
    confidence,
    expected,
)

# The ceilings as seeded in the technology table.
ADSL, VDSL, VECT = Decimal(24), Decimal(100), Decimal(300)


def mbps(value: str) -> Decimal:
    return Decimal(value)


# clamping


@pytest.mark.parametrize(
    ("advertised", "ceiling", "held", "was_clamped"),
    [
        (mbps("1000"), ADSL, ADSL, True),
        (mbps("300"), VDSL, VDSL, True),
        (mbps("24"), ADSL, mbps("24"), False),
        (mbps("8"), ADSL, mbps("8"), False),
        (mbps("1000"), None, mbps("1000"), False),
        (None, ADSL, None, False),
    ],
)
def test_a_filing_is_held_to_its_technology(
    advertised: Decimal | None, ceiling: Decimal | None,
    held: Decimal | None, was_clamped: bool,
) -> None:
    assert clamp(advertised, ceiling) == (held, was_clamped)


def test_gigabit_adsl_cannot_win() -> None:
    """Five real register rows file ADSL at >= 1 Gbps. They are stored as filed and clamped here."""
    value, was_clamped = clamp(mbps("1000"), ADSL)
    assert value == ADSL
    assert was_clamped


def test_clamping_is_reported_not_hidden() -> None:
    """The card must be able to say the operator filed something impossible."""
    assert expected("copper", mbps("1000"), ceiling=ADSL).clamped is True
    assert expected("copper", mbps("10"), ceiling=ADSL).clamped is False


# confidence


def test_no_tests_is_no_confidence() -> None:
    """Not low confidence. There is nothing to be confident about."""
    assert confidence(None) == 0.0
    assert confidence(0) == 0.0


def test_one_test_is_weak_but_not_nothing() -> None:
    assert confidence(1) == pytest.approx(MIN_CONFIDENCE)


def test_enough_tests_is_full_confidence() -> None:
    assert confidence(FULL_CONFIDENCE_TESTS) == 1.0
    assert confidence(500) == 1.0


@given(st.integers(min_value=1, max_value=200))
def test_confidence_never_falls_as_tests_accumulate(tests: int) -> None:
    assert confidence(tests) <= confidence(tests + 1) + 1e-9


# tempering by family


def test_fibre_delivers_what_it_says() -> None:
    """A cell median mixes every operator and technology, so it says nothing about a fibre line."""
    result = expected("fibre", mbps("1000"), median_mbps=mbps("60"), tests=50)
    assert result.mbps == mbps("1000")
    assert result.measured is False


def test_copper_is_held_down_by_measurement() -> None:
    """Advertised 100 where the cell measures 40 is not 100."""
    result = expected("copper", mbps("100"), ceiling=VDSL, median_mbps=mbps("40"), tests=30)
    assert result.mbps == mbps("50")
    assert result.measured is True


def test_copper_may_exceed_the_median_a_little() -> None:
    """Medians include congested evenings, so a small margin is allowed."""
    result = expected("copper", mbps("45"), ceiling=VDSL, median_mbps=mbps("40"), tests=30)
    assert result.mbps == mbps("45")


def test_copper_without_a_measurement_is_declared_only() -> None:
    result = expected("copper", mbps("100"), ceiling=VDSL)
    assert result.mbps == mbps("100")
    assert result.measured is False
    assert result.confidence == 0.0


def test_mobile_without_a_measurement_has_no_expectation() -> None:
    """An advertised mobile figure is a best case the customer will not see indoors."""
    result = expected("wireless", mbps("300"))
    assert result.mbps is None


def test_mobile_takes_an_indoor_penalty() -> None:
    result = expected("wireless", mbps("300"), median_mbps=mbps("100"), tests=30)
    assert result.mbps == mbps("80")


def test_satellite_is_discounted_from_its_headline() -> None:
    result = expected("satellite", mbps("100"))
    assert result.mbps == mbps("70")


# the clamp and the temper together


def test_an_impossible_filing_is_clamped_before_tempering() -> None:
    """ADSL filed at a gigabit, in a cell measuring 8 Mbps, is 10 Mbps and not 24."""
    result = expected("copper", mbps("1000"), ceiling=ADSL, median_mbps=mbps("8"), tests=30)
    assert result.clamped is True
    assert result.mbps == mbps("10.0")


@given(
    advertised=st.decimals(min_value=1, max_value=2000, allow_nan=False, places=1),
    median=st.decimals(min_value=1, max_value=500, allow_nan=False, places=1),
)
def test_copper_never_exceeds_its_ceiling(advertised: Decimal, median: Decimal) -> None:
    result = expected("copper", advertised, ceiling=ADSL, median_mbps=median, tests=10)
    assert result.mbps is not None
    assert result.mbps <= ADSL
