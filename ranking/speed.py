"""What an offer is expected to deliver, as distinct from what it is sold as."""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal

# A measurement may exceed an advertised copper figure a little, because medians include
# congested evenings, but it may not be ignored.
COPPER_TOLERANCE = Decimal("1.25")

# A router indoors is not a phone at the roadside.
INDOOR_PENALTY = Decimal("0.8")

# Satellite is sold at its beam peak.
SATELLITE_SHARE = Decimal("0.7")

# One test is weak evidence, twenty five is enough. Between them the curve is logarithmic,
# because the second test tells you far more than the twentieth.
MIN_CONFIDENCE = 0.45
FULL_CONFIDENCE_TESTS = 25


@dataclass(frozen=True)
class Expected:
    """A speed with its provenance attached, so a card can say why it says what it does."""

    mbps: Decimal | None
    clamped: bool
    measured: bool
    confidence: float


def clamp(advertised: Decimal | None, ceiling: Decimal | None) -> tuple[Decimal | None, bool]:
    """Hold a filing to what its technology can physically carry.

    The register files 942 services above their ceiling, five of them ADSL at a gigabit.
    Those rows are stored exactly as filed. This is where they stop winning comparisons.
    """
    if advertised is None or ceiling is None:
        return advertised, False
    if advertised <= ceiling:
        return advertised, False
    return ceiling, True


def confidence(tests: int | None) -> float:
    """How much the measurement is worth. No tests is no confidence, not low confidence."""
    if tests is None or tests <= 0:
        return 0.0
    if tests >= FULL_CONFIDENCE_TESTS:
        return 1.0
    share = math.log(tests) / math.log(FULL_CONFIDENCE_TESTS)
    return MIN_CONFIDENCE + (1.0 - MIN_CONFIDENCE) * share


def tempered(seen: Decimal, filed: Decimal | None, weight: float) -> Decimal:
    """Move from what was filed toward what was measured, by how much the measurement is worth.

    Two tests are not six and six are not twenty five, and the difference was being thrown
    away: confidence was computed, reported on the card.
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
    """Temper an advertised figure with measurement, by what the technology is."""
    held, was_clamped = clamp(advertised, ceiling)
    weight = confidence(tests)
    measured = median_mbps is not None and weight > 0.0

    if family in ("fiber", "coax"):
        # Fiber delivers what it says, so a median of everyone's traffic tells us nothing.
        return Expected(held, was_clamped, False, weight)

    if family == "copper":
        if median_mbps is None or held is None:
            return Expected(held, was_clamped, False, 0.0)
        # Held back toward the advertised figure the thinner the measurement is, and never
        # above it: a line is sold at a rate the copper either carries or does not.
        reached = min(held, median_mbps * COPPER_TOLERANCE)
        return Expected(tempered(reached, held, weight), was_clamped, True, weight)

    if family in ("wireless", "mobile"):
        # Without a measurement there is no basis at all: an advertised mobile figure is a
        # best case under conditions the customer will not have.
        if median_mbps is None:
            return Expected(None, was_clamped, False, 0.0)
        # The band filed for this place is the other witness. Neither is trusted outright:
        # the operator has an interest, and a tile of two tests is barely a measurement.
        seen = median_mbps * INDOOR_PENALTY
        return Expected(tempered(seen, filed_mbps, weight), was_clamped, True, weight)

    if family == "satellite":
        if held is None:
            return Expected(None, was_clamped, False, 0.0)
        return Expected(held * SATELLITE_SHARE, was_clamped, False, weight)

    return Expected(held, was_clamped, measured, weight)
