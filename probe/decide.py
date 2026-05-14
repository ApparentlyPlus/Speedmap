"""Decide whether an address still needs asking.

Four answers, and the difference between the last two is the whole point. A cached answer
that has expired is still evidence; an address nobody ever asked about is not. Reading the
second as the first would report no service on silence, which is how a comparison site
tells someone they cannot buy what they can.
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

# Fibre is dug street by street, so a provider selling a gigabit somewhere along a street is
# near enough to selling it at every door on it. Below that the inference does not hold:
# vectored copper varies by cabinet distance, and a slow neighbour is exactly the address
# where an upgrade might already have landed, so those are asked rather than assumed.
CONFIDENT_MBPS = Decimal(1000)

# Verdicts that need the operator asked again. Stale is included: the answer is shown while
# the check runs, rather than the address being treated as unanswerable.
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
) -> str:
    """How much is known about this address, and whether the operator need be asked.

    checked_to is how far the operator's own checker was walked up this street, and belongs
    only to the provider that was walked: pass None for every other, or their silence is
    read as a refusal they never made. A number at or below it was asked and produced
    nothing, which is a refusal. Above it, or with no scan at all, nobody ever asked.

    street_best_mbps is the fastest this same provider sells anywhere on this street. An
    answer for this exact address still beats it, because it was asked rather than reasoned.
    """
    if answer is not None and answer.expires_at > now:
        return FRESH
    if street_best_mbps is not None and street_best_mbps >= CONFIDENT_MBPS:
        return INFERRED
    if answer is not None:
        return STALE
    if street_no is not None and checked_to is not None and street_no <= checked_to:
        return REFUSED
    return UNKNOWN
