from __future__ import annotations

from decimal import Decimal

from hypothesis import given
from hypothesis import strategies as st

from ranking.cost import WINDOW_MONTHS, MonthlyCost, Price, blended, promo_window

D = Decimal
FREE = D(0)


def _price(monthly: str, promo_months: int | None = None, promo_monthly_eur: Decimal | None = None) -> Price:
    return Price(monthly_eur=D(monthly), setup_eur=FREE, hardware_eur=FREE, promo_months=promo_months,
                 promo_monthly_eur=promo_monthly_eur)


def test_blended() -> None:
    assert blended(_price("30")) == MonthlyCost(D("30"), D("30"), FREE)

    # 6 months at 20 then 18 at 30
    cost = blended(_price("30", promo_months=6, promo_monthly_eur=D("20")))
    assert cost is not None
    assert cost.total == D("27.5")

    # a 240€ router is 10 a month
    cost = blended(Price(monthly_eur=D("25"), setup_eur=D("0"), hardware_eur=D("240")))
    assert cost is not None
    assert cost.upfront == D("10")
    assert cost.total == D("35")

    cheap = Price(monthly_eur=D("25"), setup_eur=FREE, hardware_eur=D("240"))
    assert blended(cheap).total > blended(_price("30")).total


def test_blended_unknown() -> None:
    cost = blended(Price(monthly_eur=D("30"), hardware_eur=FREE))
    assert cost.total == D("30")
    assert cost.complete is False

    cost = blended(Price(monthly_eur=D("30"), setup_eur=FREE))
    assert cost.total == D("30")
    assert cost.complete is False

    # zero is known, None isn't
    cost = blended(_price("30"))
    assert cost.total == D("30")
    assert cost.complete is True


def test_promo_window() -> None:
    price = _price("30", promo_months=6)  # no rate
    assert promo_window(price) == 0
    cost = blended(price)
    assert cost is not None
    assert cost.total == D("30")

    price = _price("30", promo_months=36, promo_monthly_eur=D("20"))
    assert promo_window(price) == WINDOW_MONTHS
    cost = blended(price)
    assert cost is not None
    assert cost.total == D("20")

    cost = blended(_price("30", promo_months=WINDOW_MONTHS, promo_monthly_eur=D("20")))
    assert cost is not None
    assert cost.total == D("20")

    for months in (-1, 0):
        cost = blended(_price("30", promo_months=months, promo_monthly_eur=D("20")))
        assert cost is not None
        assert cost.total == D("30")


money = st.decimals(min_value=0, max_value=500, allow_nan=False, allow_infinity=False, places=2)


@given(monthly=money, setup=money, hardware=money)
def test_blended_floor(monthly: Decimal, setup: Decimal, hardware: Decimal) -> None:
    cost = blended(Price(monthly_eur=monthly, setup_eur=setup, hardware_eur=hardware))
    assert cost is not None
    assert cost.total >= monthly
    assert cost.recurring + cost.upfront == cost.total


@given(monthly=money, promo=money, months=st.integers(min_value=0, max_value=48))
def test_blended_promo(monthly: Decimal, promo: Decimal, months: int) -> None:
    without = blended(Price(monthly_eur=monthly, setup_eur=FREE, hardware_eur=FREE))
    with_promo = blended(Price(monthly_eur=monthly, setup_eur=FREE, hardware_eur=FREE,
                               promo_months=months, promo_monthly_eur=min(promo, monthly)))
    assert with_promo.total <= without.total
