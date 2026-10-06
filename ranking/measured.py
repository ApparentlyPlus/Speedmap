"""What people actually got near an address, which can differ from what they were sold.

Every other input to the ranking is an operator describing itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import psycopg
from psycopg.rows import TupleRow

from ranking.tile import quadkey

# which of Ookla's two families each technology falls under
WORLD = {
    "fiber": "fixed",
    "coax": "fixed",
    "copper": "fixed",
    "wireless": "mobile",
}

NEARBY = """
select distinct on (family) family, avg_down_mbps, avg_up_mbps, tests
from speed_cell
where quadkey = %s
order by family, observed_on desc
"""


@dataclass(frozen=True)
class Measured:
    """One quarter of tests in one tile, for one of Ookla's families."""

    family: str
    down_mbps: Decimal
    up_mbps: Decimal
    tests: int


def nearby(
    conn: psycopg.Connection[TupleRow], lat: float, lon: float
) -> dict[str, Measured]:
    """The latest measurements for the tile this address is in.

    A tile is about 600 m across, so this describes the street and its neighbours more than
    the address.
    """
    found: dict[str, Measured] = {}
    for family, down, up, tests in conn.execute(NEARBY, (quadkey(lat, lon),)).fetchall():
        found[str(family)] = Measured(
            family=str(family),
            down_mbps=Decimal(down),
            up_mbps=Decimal(up),
            tests=int(tests),
        )
    return found


def for_family(measured: dict[str, Measured], family: str) -> Measured | None:
    """The measurement relevant to this technology, if any."""
    world = WORLD.get(family)
    return None if world is None else measured.get(world)
