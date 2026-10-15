"""What a tariff really costs per month."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

# the usual Greek contract, so a 2 year lock compares with a rolling monthly
WINDOW_MONTHS = 24


@dataclass(frozen=True)
class Price:
    # None is unknown, never zero

    monthly_eur: Decimal
    setup_eur: Decimal | None = None
    hardware_eur: Decimal | None = None
    contract_months: int | None = None
    promo_months: int | None = None
    promo_monthly_eur: Decimal | None = None


@dataclass(frozen=True)
class MonthlyCost:
    total: Decimal
    recurring: Decimal
    upfront: Decimal
    complete: bool = True  # False if a one-off is unpublished, so the total is a floor


def promo_window(price: Price) -> int:
    # a promo longer than the window just fills it
    if price.promo_months is None or price.promo_monthly_eur is None:
        return 0
    return min(max(price.promo_months, 0), WINDOW_MONTHS)


def upfront(price: Price) -> tuple[Decimal, bool]:
    """Setup plus hardware spread over the window, and whether both were published."""
    known = price.setup_eur is not None and price.hardware_eur is not None
    setup = price.setup_eur if price.setup_eur is not None else Decimal(0)
    hardware = price.hardware_eur if price.hardware_eur is not None else Decimal(0)
    return (setup + hardware) / WINDOW_MONTHS, known


def blended(price: Price) -> MonthlyCost:
    spread, known = upfront(price)
    n = promo_window(price)
    rate = price.promo_monthly_eur if price.promo_monthly_eur is not None else Decimal(0)
    recurring = (rate * Decimal(n) + price.monthly_eur * Decimal(WINDOW_MONTHS - n)) / WINDOW_MONTHS
    return MonthlyCost(total=recurring + spread, recurring=recurring, upfront=spread, complete=known)
