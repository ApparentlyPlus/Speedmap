"""Decide whether an address still needs asking.

An expired answer is still evidence. An address nobody ever asked about isn't, and reading
the second as the first reports "no service" on silence.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

FRESH = "fresh"
INFERRED = "inferred"
STALE = "stale"
REFUSED = "refused"
UNKNOWN = "unknown"

# Fiber gets dug street by street, so fiber somewhere on a street is close enough to fiber at
# every door. Copper varies with distance to the cabinet, so it gets asked.
CONFIDENT_MBPS = Decimal(1000)

# verdicts worth asking again. stale included: the old answer shows while it runs
ASK = frozenset({STALE, REFUSED, UNKNOWN})


@dataclass(frozen=True)
class Answer:
    """What the cache holds for one address and provider."""

    serviceable: bool
    expires_at: datetime


def verdict(
    answer: Answer | None,
    *,
    now: datetime,
    street_no: int | None = None,
    checked_to: int | None = None,
    street_best_mbps: Decimal | None = None,
    street_fiber: bool = False,
    refused: bool = False,
) -> str:
    """How much is known about this address, and whether to ask the operator.

    checked_to is only for the provider whose checker was walked. Pass None for the others, or
    their silence reads as a refusal they never gave.
    """
    if answer is not None and answer.expires_at > now:
        return FRESH
    if street_fiber or (street_best_mbps is not None and street_best_mbps >= CONFIDENT_MBPS):
        return INFERRED
    if answer is not None:
        return STALE
    # asked outright and refused: there's no availability row, so without this it looks
    # like an address nobody asked about
    if refused:
        return REFUSED
    if street_no is not None and checked_to is not None and street_no <= checked_to:
        return REFUSED
    return UNKNOWN
