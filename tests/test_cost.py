"""Blending a tariff into one monthly figure."""

from __future__ import annotations

from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from ranking.cost import WINDOW_MONTHS, MonthlyCost, Price, blended, promo_window

FREE = Decimal(0)


def euros(value: str) -> Decimal:
    return Decimal(value)


def plain(monthly: str) -> Price:
    """A tariff with no promo and no fees, all of them known to be zero."""
    return Price(monthly_eur=euros(monthly), setup_eur=FREE, hardware_eur=FREE)


def test_a_flat_tariff_costs_what_it_says() -> None:
    assert blended(plain("30")) == MonthlyCost(euros("30"), euros("30"), FREE)


def test_a_promo_is_spread_across_the_window() -> None:
    """6 months at 20 then 18 at 30 is 27.50 a month, not 20 and not 30."""
    price = Price(
        monthly_eur=euros("30"), setup_eur=FREE, hardware_eur=FREE,
        promo_months=6, promo_monthly_eur=euros("20"),
    )
    cost = blended(price)
    assert cost is not None
    assert cost.total == euros("27.5")


def test_setup_and_hardware_are_spread_not_ignored() -> None:
    """A 5G router at 240 euros is 10 a month, which can outweigh a cheaper headline."""
    price = Price(monthly_eur=euros("25"), setup_eur=euros("0"), hardware_eur=euros("240"))
    cost = blended(price)
    assert cost is not None
    assert cost.upfront == euros("10")
    assert cost.total == euros("35")


def test_a_cheaper_headline_can_cost_more() -> None:
    """The reason the blend exists at all."""
    cheap = Price(monthly_eur=euros("25"), setup_eur=FREE, hardware_eur=euros("240"))
    dearer = Price(monthly_eur=euros("30"), setup_eur=FREE, hardware_eur=FREE)
    cheap_cost, dear_cost = blended(cheap), blended(dearer)
    assert cheap_cost is not None and dear_cost is not None
    assert cheap_cost.total > dear_cost.total


# unknown parts


def test_an_unknown_setup_fee_makes_the_cost_unknown() -> None:
    """A scraper that failed to find the fee has not established there isn't one."""
    assert blended(Price(monthly_eur=euros("30"), hardware_eur=FREE)) is None


def test_an_unknown_hardware_price_makes_the_cost_unknown() -> None:
    assert blended(Price(monthly_eur=euros("30"), setup_eur=FREE)) is None


def test_a_zero_fee_is_not_an_unknown_fee() -> None:
    """Zero is a fact the scraper found; null is a fact it did not."""
    assert blended(Price(monthly_eur=euros("30"), setup_eur=FREE, hardware_eur=FREE)) is not None


# promo edge cases


def test_a_promo_without_a_rate_is_not_a_promo() -> None:
    price = Price(monthly_eur=euros("30"), setup_eur=FREE, hardware_eur=FREE, promo_months=6)
    assert promo_window(price) == 0
    cost = blended(price)
    assert cost is not None
    assert cost.total == euros("30")


def test_a_promo_longer_than_the_window_fills_it() -> None:
    """Otherwise the remaining months go negative and the offer gets cheaper than free."""
    price = Price(
        monthly_eur=euros("30"), setup_eur=FREE, hardware_eur=FREE,
        promo_months=36, promo_monthly_eur=euros("20"),
    )
    assert promo_window(price) == WINDOW_MONTHS
    cost = blended(price)
    assert cost is not None
    assert cost.total == euros("20")


def test_a_promo_covering_the_whole_window_is_the_promo_rate() -> None:
    price = Price(
        monthly_eur=euros("30"), setup_eur=FREE, hardware_eur=FREE,
        promo_months=WINDOW_MONTHS, promo_monthly_eur=euros("20"),
    )
    cost = blended(price)
    assert cost is not None
    assert cost.total == euros("20")


@pytest.mark.parametrize("months", [-1, 0])
def test_a_nonsense_promo_length_is_no_promo(months: int) -> None:
    price = Price(
        monthly_eur=euros("30"), setup_eur=FREE, hardware_eur=FREE,
        promo_months=months, promo_monthly_eur=euros("20"),
    )
    cost = blended(price)
    assert cost is not None
    assert cost.total == euros("30")


# properties


money = st.decimals(min_value=0, max_value=500, allow_nan=False, allow_infinity=False, places=2)


@given(monthly=money, setup=money, hardware=money)
def test_the_blend_is_never_below_the_cheapest_month(
    monthly: Decimal, setup: Decimal, hardware: Decimal
) -> None:
    cost = blended(Price(monthly_eur=monthly, setup_eur=setup, hardware_eur=hardware))
    assert cost is not None
    assert cost.total >= monthly


@given(monthly=money, promo=money, months=st.integers(min_value=0, max_value=48))
def test_a_promo_never_raises_the_cost(monthly: Decimal, promo: Decimal, months: int) -> None:
    """A discount is a discount, whatever its length."""
    without = blended(Price(monthly_eur=monthly, setup_eur=FREE, hardware_eur=FREE))
    with_promo = blended(
        Price(
            monthly_eur=monthly, setup_eur=FREE, hardware_eur=FREE,
            promo_months=months, promo_monthly_eur=min(promo, monthly),
        )
    )
    assert without is not None and with_promo is not None
    assert with_promo.total <= without.total


@given(monthly=money, setup=money, hardware=money)
def test_the_parts_always_sum_to_the_total(
    monthly: Decimal, setup: Decimal, hardware: Decimal
) -> None:
    cost = blended(Price(monthly_eur=monthly, setup_eur=setup, hardware_eur=hardware))
    assert cost is not None
    assert cost.recurring + cost.upfront == cost.total
