"""How long an answer stays trusted, which depends on the answer.

A gigabit address is settled. A slow one is where someone's about to dig. A failure isn't an
answer, and is retried within hours.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

GIGABIT = Decimal(1000)
FAST = Decimal(300)
USABLE = Decimal(100)

SETTLED = timedelta(days=730)
LIKELY = timedelta(days=183)
CHANGING = timedelta(days=91)
# absence is the least stable answer there is: one trench overturns it
VOLATILE = timedelta(days=30)
FAILED = timedelta(hours=6)


def ttl(best_mbps: Decimal | None, *, serviceable: bool = True) -> timedelta:
    """How long to trust this answer before asking again."""
    if not serviceable or best_mbps is None:
        return VOLATILE
    if best_mbps >= GIGABIT:
        return SETTLED
    if best_mbps >= FAST:
        return LIKELY
    if best_mbps >= USABLE:
        return CHANGING
    return VOLATILE
