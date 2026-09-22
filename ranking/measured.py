"""What people actually got near an address, as distinct from what they were sold.

Every other input to a ranking is an operator describing itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import psycopg
from psycopg.rows import TupleRow

from ranking.tile import quadkey

# Which of Ookla's two worlds a technology of ours lives in.
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
    """One quarter of tests in one tile, for one of Ookla's two worlds."""

    family: str
    down_mbps: Decimal
    up_mbps: Decimal
    tests: int


def nearby(
    conn: psycopg.Connection[TupleRow], lat: float, lon: float
) -> dict[str, Measured]:
    """The most recent measurements for the tile this address falls in.

    A tile is about 600 m across, so this is the street and the few around it rather than
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
    """The measurement that speaks to this technology, if there is one."""
    world = WORLD.get(family)
    return None if world is None else measured.get(world)
