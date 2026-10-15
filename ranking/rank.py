"""Order what someone can buy at an address. Past ENOUGH_MBPS speed stops mattering."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ranking.cost import MonthlyCost

# a judgement call, not a technical limit
ENOUGH_MBPS = Decimal(100)

HOUSEHOLD_GB = 200  # a month of household streaming, in GB

# tie-break: a cell shares capacity with the whole street at 7pm, a line doesn't
STEADINESS = {"fiber": 0, "coax": 1, "copper": 2, "wireless": 3, "satellite": 4}
UNSTEADY = len(STEADINESS)

ENOUGH = "covers an ordinary household"
BEST = "the steadiest connection here that covers a household"
FASTEST = "the fastest here, and short of what a household wants"
SHORT = "short of what a household wants"
FROM = "the setup fee is not published, so this is what it costs or more"


@dataclass(frozen=True)
class Option:
    provider: str
    provider_name: str  # the brand, not always the same word as the code
    plan: str
    technology: str
    family: str
    expected_mbps: Decimal | None
    cost: MonthlyCost
    data_cap_gb: int | None = None
    basis: str = "advertised"  # where expected_mbps came from
    confidence: float = 0.0  # evidence from speed tests only
    tests: int = 0


@dataclass(frozen=True)
class Ranked:
    option: Option
    enough: bool
    why: str


def steadiness(family: str) -> int:
    return STEADINESS.get(family, UNSTEADY)


def enough_for(option: Option, need: Decimal) -> bool:
    # unknown speed never clears the bar
    if option.data_cap_gb is not None and option.data_cap_gb < HOUSEHOLD_GB:
        return False
    return option.expected_mbps is not None and option.expected_mbps >= need


def order(option: Option, need: Decimal) -> tuple[int, Decimal, Decimal, Decimal]:
    # two groups, so nothing fast enough sits below something that isn't
    speed = option.expected_mbps if option.expected_mbps is not None else Decimal(0)
    if enough_for(option, need):
        # all fast enough, so the question is what it runs on, then the price
        return (0, Decimal(steadiness(option.family)), option.cost.total, -speed)
    # none fast enough, so speed decides and price breaks ties
    return (1, -speed, Decimal(steadiness(option.family)), option.cost.total)


def rank(options: list[Option], need: Decimal = ENOUGH_MBPS) -> list[Ranked]:
    out: list[Ranked] = []
    for i, o in enumerate(sorted(options, key=lambda o: order(o, need))):
        ok = enough_for(o, need)
        if not o.cost.complete:
            why = FROM
        elif ok:
            why = BEST if i == 0 else ENOUGH
        else:
            why = FASTEST if i == 0 else SHORT
        out.append(Ranked(option=o, enough=ok, why=why))
    return out
