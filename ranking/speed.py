"""Expected speed of an offer, tempered by measurement."""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal

# medians include congested evenings, so let copper beat its advert a bit
COPPER_TOLERANCE = Decimal("1.25")

# a router indoors gets less than a phone at the roadside
INDOOR_PENALTY = Decimal("0.8")

SATELLITE_SHARE = Decimal("0.7")  # satellite is sold at its beam peak

# log scale between 1 test and 25, the second test says more than the twentieth
MIN_CONFIDENCE = 0.45
FULL_CONFIDENCE_TESTS = 25


@dataclass(frozen=True)
class Expected:
    mbps: Decimal | None
    clamped: bool
    measured: bool
    confidence: float


def clamp(advertised: Decimal | None, ceiling: Decimal | None) -> tuple[Decimal | None, bool]:
    # the register has 942 services filed above their ceiling, five are gigabit ADSL
    if advertised is None or ceiling is None:
        return advertised, False
    if advertised <= ceiling:
        return advertised, False
    return ceiling, True


def confidence(tests: int | None) -> float:
    if tests is None or tests <= 0:
        return 0.0
    if tests >= FULL_CONFIDENCE_TESTS:
        return 1.0
    share = math.log(tests) / math.log(FULL_CONFIDENCE_TESTS)
    return MIN_CONFIDENCE + (1.0 - MIN_CONFIDENCE) * share


def tempered(seen: Decimal, filed: Decimal | None, weight: float) -> Decimal:
    """Move from the filed figure toward the measured one by weight."""
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
    held, was_clamped = clamp(advertised, ceiling)
    weight = confidence(tests)
    measured = median_mbps is not None and weight > 0.0

    if family in ("fiber", "coax"):
        # fiber delivers what it's sold at
        return Expected(held, was_clamped, False, weight)

    if family == "copper":
        if median_mbps is None or held is None:
            return Expected(held, was_clamped, False, 0.0)
        # never above the advert, and closer to it the thinner the measurement
        reached = min(held, median_mbps * COPPER_TOLERANCE)
        return Expected(tempered(reached, held, weight), was_clamped, True, weight)

    if family in ("wireless", "mobile"):
        # an advertised mobile figure is a best case nobody gets
        if median_mbps is None:
            return Expected(None, was_clamped, False, 0.0)
        # trust neither outright, the operator has an interest and 2 tests is barely a sample
        seen = median_mbps * INDOOR_PENALTY
        return Expected(tempered(seen, filed_mbps, weight), was_clamped, True, weight)

    if family == "satellite":
        if held is None:
            return Expected(None, was_clamped, False, 0.0)
        return Expected(held * SATELLITE_SHARE, was_clamped, False, weight)

    return Expected(held, was_clamped, measured, weight)
