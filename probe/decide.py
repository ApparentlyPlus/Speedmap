"""Does an address still need asking."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

FRESH = "fresh"
INFERRED = "inferred"
STALE = "stale"
REFUSED = "refused"
UNKNOWN = "unknown"

# fiber is dug per street so a gigabit anywhere on it will do, copper depends on the cabinet
CONFIDENT_MBPS = Decimal(1000)

# stale too, the old answer shows meanwhile
ASK = frozenset({STALE, REFUSED, UNKNOWN})


@dataclass(frozen=True)
class Answer:
    serviceable: bool
    expires_at: datetime


def verdict(answer: Answer | None, *, now: datetime, street_no: int | None = None, checked_to: int | None = None,
            street_best_mbps: Decimal | None = None, street_fiber: bool = False, refused: bool = False) -> str:
    """checked_to only for the provider that was walked, None for the rest."""
    if answer is not None and answer.expires_at > now:
        return FRESH
    if street_fiber or (street_best_mbps is not None and street_best_mbps >= CONFIDENT_MBPS):
        return INFERRED
    if answer is not None:
        return STALE
    # refusals leave no availability row
    if refused:
        return REFUSED
    if street_no is not None and checked_to is not None and street_no <= checked_to:
        return REFUSED
    return UNKNOWN
