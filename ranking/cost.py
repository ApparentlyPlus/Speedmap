"""Normalise a tariff to what it actually costs per month."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

# Everything is blended over the same window, so a two-year lock and a rolling monthly
# contract can be compared. Twenty four months is the usual Greek contract length.
WINDOW_MONTHS = 24


@dataclass(frozen=True)
class Price:
    """A tariff as filed. None means not known, never zero: a scraper that failed to find
    the setup fee has not established that there isn't one."""

    monthly_eur: Decimal
    setup_eur: Decimal | None = None
    hardware_eur: Decimal | None = None
    contract_months: int | None = None
    promo_months: int | None = None
    promo_monthly_eur: Decimal | None = None


@dataclass(frozen=True)
class MonthlyCost:
    """The blend, kept in parts so a card can show why a cheap headline is not cheap."""

    total: Decimal
    recurring: Decimal
    upfront: Decimal


def promo_window(price: Price) -> int:
    """Promo months counted inside the window. A promo longer than the window is the whole
    window: charging the post-promo rate for negative months would make the offer cheaper."""
    if price.promo_months is None or price.promo_monthly_eur is None:
        return 0
    return min(max(price.promo_months, 0), WINDOW_MONTHS)


def upfront(price: Price) -> Decimal | None:
    """Setup plus hardware, spread over the window. None if either is unknown."""
    if price.setup_eur is None or price.hardware_eur is None:
        return None
    return (price.setup_eur + price.hardware_eur) / WINDOW_MONTHS


def blended(price: Price) -> MonthlyCost | None:
    """What the offer costs per month across the window, or None when a part is unknown.

    An offer with an unknown cost is not free and not expensive: it cannot be ranked by
    value, and the caller must show it without a position rather than guess one.
    """
    spread = upfront(price)
    if spread is None:
        return None

    promo = promo_window(price)
    remaining = WINDOW_MONTHS - promo
    promo_rate = price.promo_monthly_eur if price.promo_monthly_eur is not None else Decimal(0)

    recurring = (
        promo_rate * Decimal(promo) + price.monthly_eur * Decimal(remaining)
    ) / WINDOW_MONTHS
    return MonthlyCost(total=recurring + spread, recurring=recurring, upfront=spread)
