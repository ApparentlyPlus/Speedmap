"""What an offer should be expected to deliver, which can differ from what it's sold as."""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal

# A measurement may beat advertised copper a little, since medians include congested
# evenings. It can't be ignored though.
COPPER_TOLERANCE = Decimal("1.25")

# a router indoors gets less than a phone at the roadside
INDOOR_PENALTY = Decimal("0.8")

SATELLITE_SHARE = Decimal("0.7")  # satellite is sold at its beam peak

# One test is weak evidence, 25 is enough. Logarithmic in between, since the second test
# tells you far more than the twentieth.
MIN_CONFIDENCE = 0.45
FULL_CONFIDENCE_TESTS = 25


@dataclass(frozen=True)
class Expected:
    """A speed with its provenance, so a card can say why it says what it does."""

    mbps: Decimal | None
    clamped: bool
    measured: bool
    confidence: float


def clamp(advertised: Decimal | None, ceiling: Decimal | None) -> tuple[Decimal | None, bool]:
    """Hold a filing to what its technology can physically carry.

    The register files 942 services above their ceiling, five of them ADSL at a gigabit. They're
    stored as filed. This is where they stop winning comparisons.
    """
    if advertised is None or ceiling is None:
        return advertised, False
    if advertised <= ceiling:
        return advertised, False
    return ceiling, True


def confidence(tests: int | None) -> float:
    """How much a measurement is worth. No tests is zero confidence, a separate case from low."""
    if tests is None or tests <= 0:
        return 0.0
    if tests >= FULL_CONFIDENCE_TESTS:
        return 1.0
    share = math.log(tests) / math.log(FULL_CONFIDENCE_TESTS)
    return MIN_CONFIDENCE + (1.0 - MIN_CONFIDENCE) * share


def tempered(seen: Decimal, filed: Decimal | None, weight: float) -> Decimal:
    """Move from the filed figure toward the measured one, by how much the measurement is worth.

    Two tests aren't six and six aren't 25. Confidence used to be computed and shown on the card
    while the speed ignored it.
    """
    if filed is None:
        return seen
    return seen + (filed - seen) * Decimal(str(1.0 - weight))


def expected(
    family: str,
    advertised: Decimal | None,
    ceiling: Decimal | None = None,
    median_mbps: Decimal | None = None,
    tests: int | None = None,
    filed_mbps: Decimal | None = None,
) -> Expected:
    """Temper an advertised figure with measurement, according to the technology."""
    held, was_clamped = clamp(advertised, ceiling)
    weight = confidence(tests)
    measured = median_mbps is not None and weight > 0.0

    if family in ("fiber", "coax"):
        # fiber delivers what it's sold at, so a median of everyone's traffic says nothing
        return Expected(held, was_clamped, False, weight)

    if family == "copper":
        if median_mbps is None or held is None:
            return Expected(held, was_clamped, False, 0.0)
        # Pulled toward the advertised figure the thinner the measurement, and never above it:
        # copper either carries the sold rate or doesn't.
        reached = min(held, median_mbps * COPPER_TOLERANCE)
        return Expected(tempered(reached, held, weight), was_clamped, True, weight)

    if family in ("wireless", "mobile"):
        # No measurement, no basis. An advertised mobile figure is a best case under conditions
        # the customer won't have.
        if median_mbps is None:
            return Expected(None, was_clamped, False, 0.0)
        # The filed band is the other witness. Neither is trusted outright: the operator has
        # an interest, and a two-test tile is barely a measurement.
        seen = median_mbps * INDOOR_PENALTY
        return Expected(tempered(seen, filed_mbps, weight), was_clamped, True, weight)

    if family == "satellite":
        if held is None:
            return Expected(None, was_clamped, False, 0.0)
        return Expected(held * SATELLITE_SHARE, was_clamped, False, weight)

    return Expected(held, was_clamped, measured, weight)
