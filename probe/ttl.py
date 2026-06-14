"""How long an answer is worth keeping, which depends on what the answer was.

A gigabit address is settled: fibre is not dug up again, and only a new operator arriving
changes what is true there. A slow address is the least stable thing on the map, because it
is precisely where someone is building. Caching both for the same period would either throw
away good answers or serve stale ones, and it is the slow addresses that matter most.

A failure is not an answer and is never cached as one. It is retried in hours, not months.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

GIGABIT = Decimal(1000)
FAST = Decimal(300)
USABLE = Decimal(100)

# Fibre is not removed. Only a new operator changes the answer.
SETTLED = timedelta(days=730)
# Likely fibre, and upgrades are plausible.
LIKELY = timedelta(days=183)
# Vectoring or early fibre, actively changing.
CHANGING = timedelta(days=91)
# Exactly the addresses an altnet is building toward, and absence is the least stable
# answer of all: it is the one a single trench overturns.
VOLATILE = timedelta(days=30)
# Not an answer. Ask again today.
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
