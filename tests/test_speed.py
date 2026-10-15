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
    tempered,
)

D = Decimal
ADSL, VDSL, VECT = D(24), D(100), D(300)  # ceilings as seeded in technology


def test_clamp() -> None:
    for advertised, ceiling, held, was_clamped in [
        (D("1000"), ADSL, ADSL, True),
        (D("300"), VDSL, VDSL, True),
        (D("24"), ADSL, D("24"), False),
        (D("8"), ADSL, D("8"), False),
        (D("1000"), None, D("1000"), False),
        (None, ADSL, None, False),
    ]:
        assert clamp(advertised, ceiling) == (held, was_clamped)

    # five register rows really file gigabit ADSL
    value, was_clamped = clamp(D("1000"), ADSL)
    assert value == ADSL
    assert was_clamped
    assert expected("copper", D("1000"), ceiling=ADSL).clamped is True
    assert expected("copper", D("10"), ceiling=ADSL).clamped is False


def test_confidence() -> None:
    assert confidence(None) == 0.0
    assert confidence(0) == 0.0
    assert confidence(1) == pytest.approx(MIN_CONFIDENCE)
    assert confidence(FULL_CONFIDENCE_TESTS) == 1.0
    assert confidence(500) == 1.0


@given(st.integers(min_value=1, max_value=200))
def test_confidence_rises(tests: int) -> None:
    assert confidence(tests) <= confidence(tests + 1) + 1e-9


def test_expected() -> None:
    e = expected("fiber", D("1000"), median_mbps=D("60"), tests=50)
    assert e.mbps == D("1000")
    assert e.measured is False

    e = expected("copper", D("100"), ceiling=VDSL, median_mbps=D("40"), tests=30)
    assert e.mbps == D("50")
    assert e.measured is True

    # a bit over the median is allowed
    e = expected("copper", D("45"), ceiling=VDSL, median_mbps=D("40"), tests=30)
    assert e.mbps == D("45")

    e = expected("copper", D("100"), ceiling=VDSL)
    assert e.mbps == D("100")
    assert e.measured is False
    assert e.confidence == 0.0

    assert expected("wireless", D("300")).mbps is None
    assert expected("wireless", D("300"), median_mbps=D("100"), tests=30).mbps == D("80")
    assert expected("satellite", D("100")).mbps == D("70")

    # gigabit ADSL in a tile measuring 8
    e = expected("copper", D("1000"), ceiling=ADSL, median_mbps=D("8"), tests=30)
    assert e.clamped is True
    assert e.mbps == D("10.0")


@given(
    advertised=st.decimals(min_value=1, max_value=2000, allow_nan=False, places=1),
    median=st.decimals(min_value=1, max_value=500, allow_nan=False, places=1),
)
def test_expected_copper_ceiling(advertised: Decimal, median: Decimal) -> None:
    e = expected("copper", advertised, ceiling=ADSL, median_mbps=median, tests=10)
    assert e.mbps is not None
    assert e.mbps <= ADSL


def test_expected_tempered() -> None:
    # 2 tests at 36 against a band filed at 300
    e = expected("mobile", D("1000"), median_mbps=D("35.7"), tests=2, filed_mbps=D("300"))
    assert e.mbps is not None
    assert D("100") < e.mbps < D("300")

    e = expected("mobile", D("1000"), median_mbps=D("35.7"), tests=FULL_CONFIDENCE_TESTS, filed_mbps=D("300"))
    assert e.mbps == D("35.7") * D("0.8")

    seen: list[Decimal] = []
    for n in (1, 2, 6, 12, 25):
        e = expected("mobile", D("1000"), median_mbps=D("30"), tests=n, filed_mbps=D("300"))
        assert e.mbps is not None
        seen.append(e.mbps)
    assert seen == sorted(seen, reverse=True)

    # no band filed off the grid
    e = expected("mobile", D("1000"), median_mbps=D("50"), tests=2)
    assert e.mbps == D("50") * D("0.8")

    thin = expected("copper", D("100"), ceiling=D("100"), median_mbps=D("20"), tests=2)
    thick = expected("copper", D("100"), ceiling=D("100"), median_mbps=D("20"), tests=FULL_CONFIDENCE_TESTS)
    assert thin.mbps is not None
    assert thick.mbps is not None
    assert thick.mbps < thin.mbps < D("100")

    assert tempered(D("42"), None, 0.1) == D("42")


@given(
    seen=st.decimals(min_value=1, max_value=1000, allow_nan=False, places=1),
    filed=st.decimals(min_value=1, max_value=1000, allow_nan=False, places=1),
    weight=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
)
def test_tempered_between(seen: Decimal, filed: Decimal, weight: float) -> None:
    t = tempered(seen, filed, weight)
    assert min(seen, filed) - D("0.001") <= t <= max(seen, filed) + D("0.001")
