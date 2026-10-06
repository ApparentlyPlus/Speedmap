"""Normalise a tariff to what it really costs per month."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

# One window for everything, so a two-year lock and a rolling monthly can be compared.
# 24 months is the usual Greek contract.
WINDOW_MONTHS = 24


@dataclass(frozen=True)
class Price:
    """A tariff as filed. None means unknown, never zero: a scraper that missed the setup fee
    hasn't shown there isn't one."""

    monthly_eur: Decimal
    setup_eur: Decimal | None = None
    hardware_eur: Decimal | None = None
    contract_months: int | None = None
    promo_months: int | None = None
    promo_monthly_eur: Decimal | None = None


@dataclass(frozen=True)
class MonthlyCost:
    """The blend, kept in parts so a card can show why a cheap headline isn't cheap."""

    total: Decimal
    recurring: Decimal
    upfront: Decimal
    # Whether every one-off was published. If not, the total is a floor: the monthly is known
    # and a one-off isn't, so the real figure is this or more.
    complete: bool = True


def promo_window(price: Price) -> int:
    """Promo months inside the window. A promo longer than the window fills it: charging the
    post-promo rate for negative months would make the offer cheaper."""
    if price.promo_months is None or price.promo_monthly_eur is None:
        return 0
    return min(max(price.promo_months, 0), WINDOW_MONTHS)


def upfront(price: Price) -> tuple[Decimal, bool]:
    """Setup plus hardware spread over the window, and whether both were published.

    A missing part counts as zero and is flagged, so one unknown fee doesn't hide the whole price.
    """
    known = price.setup_eur is not None and price.hardware_eur is not None
    setup = price.setup_eur if price.setup_eur is not None else Decimal(0)
    hardware = price.hardware_eur if price.hardware_eur is not None else Decimal(0)
    return (setup + hardware) / WINDOW_MONTHS, known


def blended(price: Price) -> MonthlyCost:
    """Monthly cost across the window. Always a figure, since plan_price requires the monthly rate."""
    spread, known = upfront(price)

    promo = promo_window(price)
    remaining = WINDOW_MONTHS - promo
    promo_rate = price.promo_monthly_eur if price.promo_monthly_eur is not None else Decimal(0)

    recurring = (
        promo_rate * Decimal(promo) + price.monthly_eur * Decimal(remaining)
    ) / WINDOW_MONTHS
    return MonthlyCost(
        total=recurring + spread, recurring=recurring, upfront=spread, complete=known
    )
