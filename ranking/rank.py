"""Order what someone can actually buy at an address.

Speed stops mattering once there is enough of it. A household streams, calls and browses on
well under a hundred megabits, so above that line more speed is a number on a bill rather
than a difference anyone notices, and offers that clear it compete on price alone. Below it
speed is the whole question and price is the tie-break, because the choice is no longer
which good option but which least bad one.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ranking.cost import MonthlyCost

# What an ordinary household actually uses. Not a technical limit: a judgement about when
# the next rung stops being worth paying for.
ENOUGH_MBPS = Decimal(100)

# A month of household streaming, in gigabytes. A data plan below this is a phone plan
# pointed at a router: it is fast, it is cheap, and it runs out in the second week, which no
# speed makes up for. An unlimited plan states no cap and is never measured against this.
HOUSEHOLD_GB = 200

# Which to prefer when two offers are otherwise equal. A line in the ground does not share
# its capacity with the neighbourhood at seven in the evening; a cell does. A dish adds a
# second of sky and stops in weather. None of this shows up in a speed or a price.
STEADINESS = {"fibre": 0, "coax": 1, "copper": 2, "wireless": 3, "satellite": 4}
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
    # What a customer would recognise. The code is what every join uses; this is what the
    # reader is shown, and they are not always the same word.
    provider_name: str
    plan: str
    technology: str
    family: str
    expected_mbps: Decimal | None
    cost: MonthlyCost
    data_cap_gb: int | None = None
    # Where the speed came from, so a card can say why it says what it does.
    basis: str = "advertised"
    # Evidence from tests, and nothing else. A figure an operator quoted for this exact
    # line is the most specific thing here and still has a confidence of zero, because no
    # one measured it: the two say different things and neither replaces the other.
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
    """Whether this clears the bar, on speed and on how long it lasts.

    An unknown speed never clears it: not knowing how fast a wireless link is here is not
    evidence that it is fast enough. A metered plan under a household's month does not
    clear it either, however fast it runs while it lasts.
    """
    if option.data_cap_gb is not None and option.data_cap_gb < HOUSEHOLD_GB:
        return False
    return option.expected_mbps is not None and option.expected_mbps >= need


def order(option: Option, need: Decimal) -> tuple[int, Decimal, Decimal, Decimal]:
    """The sort key, in two groups, so what is fast enough never sits under what is not.

    There used to be a third group below both, for offers with no cost at all. There are
    none now: a missing setup fee leaves the monthly rate standing and only makes the total
    a floor, so everything can be placed. Three plans were being dropped to the bottom of
    the page over a number smaller than a euro and a half a month.
    """
    speed = option.expected_mbps if option.expected_mbps is not None else Decimal(0)
    if enough_for(option, need):
        # Everything here is fast enough, so the question is what it is carried on and then
        # what it costs. A line that covers a household beats a cell that also covers it,
        # even for a few euros more: the cell is shared with the street at seven in the
        # evening and the line is not, and no price comparison shows that.
        return (0, Decimal(steadiness(option.family)), option.cost.total, -speed)
    # Nothing here is fast enough, so speed is the question and cost breaks the tie.
    return (1, -speed, Decimal(steadiness(option.family)), option.cost.total)


def rank(options: list[Option], need: Decimal = ENOUGH_MBPS) -> list[Ranked]:
    """Best first. Everything is placed, because everything now has a price."""
    placed = sorted(options, key=lambda o: order(o, need))

    ranked: list[Ranked] = []
    for index, option in enumerate(placed):
        clears = enough_for(option, need)
        if not option.cost.complete:
            why = FROM
        elif clears:
            why = BEST if index == 0 else ENOUGH
        else:
            why = FASTEST if index == 0 else SHORT
        ranked.append(Ranked(option=option, enough=clears, why=why))
    return ranked
