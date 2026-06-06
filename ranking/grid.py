"""What the mobile network actually reaches an address with, per operator.

A data plan is only a fallback if the operator's own network is any good where the router
will sit, and the register says so cell by cell: the same 100 m grid the fixed wireless step
reads, taken from the mobile flags it deliberately ignored. Without this a 30€ unlimited SIM
ranks identically in a city and on a mountain, and it is worth nothing on the mountain.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import psycopg
from psycopg.rows import TupleRow

# The band is a range and the floor of it is the honest half: a cell filed at 300-1000 is
# promised to reach 300, and the rest is the operator's good fortune rather than a claim.
REACH = """
with here as (
    select floor(st_x(p.g) / 100)::int || '|' || floor(st_y(p.g) / 100)::int as gridid
    from address a
    cross join lateral (select st_transform(a.geom::geometry, 2100) as g) p
    where a.id = %s
)
select pr.code,
       bool_or(w.tech5gm = 1),
       max(sb.min_mbps),
       max(sb.max_mbps)
from raw_wireless_grid w
join here h on h.gridid = w.gridid
join provider pr on pr.register_id = w.servprov
left join speed_band sb on sb.id = nullif(w.maxdown, 0)
where w.tech4gm = 1 or w.tech5gm = 1
group by pr.code
"""


@dataclass(frozen=True)
class Reach:
    """One operator's mobile network at one address."""

    provider: str
    five_g: bool
    floor_mbps: Decimal | None
    # The top of the band this operator filed here. A tile of tests says what the place can
    # do; this says what this operator does in it, and the two are not the same claim when
    # one operator's mast is good and another's is not.
    ceiling_mbps: Decimal | None = None


def mobile(conn: psycopg.Connection[TupleRow], address_id: int) -> dict[str, Reach]:
    """Each operator's mobile reach here, by provider code.

    An operator absent from the answer does not cover this cell at all, which is a stronger
    statement than a slow band and is why absence is not filled in with a zero.
    """
    found: dict[str, Reach] = {}
    for code, five_g, floor_mbps, ceiling_mbps in conn.execute(
        REACH, (address_id,)
    ).fetchall():
        found[str(code)] = Reach(
            provider=str(code),
            five_g=bool(five_g),
            floor_mbps=None if floor_mbps is None else Decimal(floor_mbps),
            ceiling_mbps=None if ceiling_mbps is None else Decimal(ceiling_mbps),
        )
    return found
