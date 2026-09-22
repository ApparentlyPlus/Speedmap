"""Decide whether an address still needs asking.

An expired answer is still evidence. An address nobody ever asked about is not. Reading the
second as the first reports no service on silence.
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

# Fiber is dug street by street, so fiber somewhere along a street is near enough to fiber
# at every door. Copper varies by cabinet distance and is asked rather than assumed.
CONFIDENT_MBPS = Decimal(1000)

# Verdicts that need asking again. Stale is here: the old answer is shown while it runs.
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
    """How much is known about this address, and whether the operator need be asked.

    checked_to belongs only to the provider whose checker was walked. Pass None for the rest
    or their silence reads as a refusal they never made.
    """
    if answer is not None and answer.expires_at > now:
        return FRESH
    if street_fiber or (street_best_mbps is not None and street_best_mbps >= CONFIDENT_MBPS):
        return INFERRED
    if answer is not None:
        return STALE
    # Asked outright and declined. That leaves no availability row, so without this it
    # looks like an address nobody ever sought.
    if refused:
        return REFUSED
    if street_no is not None and checked_to is not None and street_no <= checked_to:
        return REFUSED
    return UNKNOWN
