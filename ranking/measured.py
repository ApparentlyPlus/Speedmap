"""Ookla measurements near an address, the one input operators don't write themselves."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import psycopg
from psycopg.rows import TupleRow

from ranking.tile import quadkey

# Ookla only has fixed and mobile
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
    family: str
    down_mbps: Decimal
    up_mbps: Decimal
    tests: int


def nearby(conn: psycopg.Connection[TupleRow], lat: float, lon: float) -> dict[str, Measured]:
    # a tile is ~600 m across, so this is the neighbourhood more than the address
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
    world = WORLD.get(family)
    return None if world is None else measured.get(world)
