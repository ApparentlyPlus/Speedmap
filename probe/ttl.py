"""How long an answer is trusted. A gigabit is settled, a slow line is where someone's about to dig."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

GIGABIT = Decimal(1000)
FAST = Decimal(300)
USABLE = Decimal(100)

SETTLED = timedelta(days=730)
LIKELY = timedelta(days=183)
CHANGING = timedelta(days=91)
VOLATILE = timedelta(days=30)  # one trench overturns a no
FAILED = timedelta(hours=6)


def ttl(best_mbps: Decimal | None, *, serviceable: bool = True) -> timedelta:
    if not serviceable or best_mbps is None:
        return VOLATILE
    if best_mbps >= GIGABIT:
        return SETTLED
    if best_mbps >= FAST:
        return LIKELY
    if best_mbps >= USABLE:
        return CHANGING
    return VOLATILE
