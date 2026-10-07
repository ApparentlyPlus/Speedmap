"""What each operator's mobile network reaches an address with.

A data plan is only a fallback if the operator's network is any good where the router sits.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import psycopg
from psycopg.rows import TupleRow

# The band's floor is the honest half: a cell filed at 300-1000 promises 300, and the rest is
# the operator's luck.
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
    ceiling_mbps: Decimal | None = None  # top of the band this operator filed here


def mobile(conn: psycopg.Connection[TupleRow], address_id: int) -> dict[str, Reach]:
    """Each operator's mobile reach here, by provider code.

    An operator missing from the answer doesn't cover this cell at all, a stronger claim than a
    slow band, which is why absence isn't filled in with zero.
    """
    found: dict[str, Reach] = {}
    for code, five_g, floor_mbps, ceiling_mbps in conn.execute(REACH, (address_id,)).fetchall():
        found[str(code)] = Reach(
            provider=str(code),
            five_g=bool(five_g),
            floor_mbps=None if floor_mbps is None else Decimal(floor_mbps),
            ceiling_mbps=None if ceiling_mbps is None else Decimal(ceiling_mbps),
        )
    return found
