"""Order what someone can buy at an address.

Speed stops mattering once there's enough of it.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ranking.cost import MonthlyCost

# What an ordinary household uses. A judgement about when the next rung stops being worth
# paying for, with no technical limit behind it.
ENOUGH_MBPS = Decimal(100)

# a month of household streaming, in GB
HOUSEHOLD_GB = 200

# Tie-break between otherwise equal offers. A line in the ground doesn't share capacity with
# the neighbourhood at seven in the evening. A cell does.
STEADINESS = {"fiber": 0, "coax": 1, "copper": 2, "wireless": 3, "satellite": 4}
UNSTEADY = len(STEADINESS)

ENOUGH = "covers an ordinary household"
BEST = "the steadiest connection here that covers a household"
FASTEST = "the fastest here, and short of what a household wants"
SHORT = "short of what a household wants"
FROM = "the setup fee is not published, so this is what it costs or more"


@dataclass(frozen=True)
class Option:
    """One thing that could be bought here."""

    provider: str
    # The brand a customer recognises. The code is the join key, and the two aren't always
    # the same word.
    provider_name: str
    plan: str
    technology: str
    family: str
    expected_mbps: Decimal | None
    cost: MonthlyCost
    data_cap_gb: int | None = None
    # where the speed came from, so a card can explain itself
    basis: str = "advertised"
    # evidence from speed tests only
    confidence: float = 0.0
    tests: int = 0


@dataclass(frozen=True)
class Ranked:
    option: Option
    enough: bool
    why: str


def steadiness(family: str) -> int:
    return STEADINESS.get(family, UNSTEADY)


def enough_for(option: Option, need: Decimal) -> bool:
    """Whether this clears the bar on speed and on data allowance.

    An unknown speed never clears it. Not knowing how fast a wireless link is here is no evidence
    that it's fast enough.
    """
    if option.data_cap_gb is not None and option.data_cap_gb < HOUSEHOLD_GB:
        return False
    return option.expected_mbps is not None and option.expected_mbps >= need


def order(option: Option, need: Decimal) -> tuple[int, Decimal, Decimal, Decimal]:
    """Sort key in two groups, so nothing fast enough sits below something that isn't.

    A third group below both used to hold offers with no cost at all.
    """
    speed = option.expected_mbps if option.expected_mbps is not None else Decimal(0)
    if enough_for(option, need):
        # all fast enough, so the question is what it runs on, then the price
        return (0, Decimal(steadiness(option.family)), option.cost.total, -speed)
    # none fast enough, so speed decides and price breaks ties
    return (1, -speed, Decimal(steadiness(option.family)), option.cost.total)


def rank(options: list[Option], need: Decimal = ENOUGH_MBPS) -> list[Ranked]:
    """Best first. Everything gets placed, since everything now has a price."""
    ordered = sorted(options, key=lambda o: order(o, need))

    out: list[Ranked] = []
    for index, option in enumerate(ordered):
        clears = enough_for(option, need)
        if not option.cost.complete:
            why = FROM
        elif clears:
            why = BEST if index == 0 else ENOUGH
        else:
            why = FASTEST if index == 0 else SHORT
        out.append(Ranked(option=option, enough=clears, why=why))
    return out
