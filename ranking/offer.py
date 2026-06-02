"""Assemble what is actually buyable at one address, priced and speed-tempered.

Three kinds of thing end up here and they qualify differently. A line qualifies because the
operator files coverage at this address. A data plan qualifies because the operator's mobile
network reaches this cell, which the fixed coverage says nothing about. A dish qualifies
everywhere, which is the whole point of it and the reason it is the last resort rather than
an absent one.
"""

from __future__ import annotations

from decimal import Decimal

import psycopg
from psycopg.rows import TupleRow

from ranking.cost import Price, blended
from ranking.grid import mobile
from ranking.rank import Option
from ranking.speed import expected

# Sold from everywhere there is sky, so it is never filtered out by coverage.
EVERYWHERE = frozenset({"satellite"})

# Bought as airtime and pointed at a router, so what qualifies it is the mobile grid.
AIRTIME = "MOBILE"

PLANS = """
select pr.code, pl.name, pl.technology, pl.family, pl.down_mbps,
       pl.needs_hardware, pl.data_cap_gb, t.max_plausible_mbps,
       pc.monthly_eur, pc.setup_eur, pc.hardware_eur,
       pc.promo_months, pc.promo_monthly_eur,
       v.avg_down_mbps,
       sb.min_mbps
from plan pl
join provider pr on pr.id = pl.provider_id
join plan_current pc on pc.plan_id = pl.id
join technology t on t.code = pl.technology
left join availability v
       on v.address_id = %(address)s and v.provider_id = pl.provider_id
      and v.technology = pl.technology and v.serviceable
left join address_coverage ac
       on ac.address_id = %(address)s and ac.provider_id = pl.provider_id
      and ac.technology = pl.technology
left join speed_band sb on sb.id = ac.speed_band_id
where pl.technology = %(airtime)s
   or pl.family = any(%(everywhere)s)
   or v.address_id is not null
   or ac.address_id is not null
"""


def speed(
    family: str,
    advertised: Decimal | None,
    ceiling: Decimal | None,
    quoted: Decimal | None,
    filed: Decimal | None,
) -> Decimal | None:
    """What this offer should be expected to deliver here.

    An operator's own per-line quote is used as it stands. It is not a crowd median taken
    across congested evenings, so the tolerance that exists to forgive those does not apply
    to it: the operator is telling us what this line carries, and it cannot carry more than
    it is sold as either.
    """
    if quoted is not None and advertised is not None:
        return min(advertised, quoted)
    if quoted is not None:
        return quoted
    reached = expected(family, advertised, ceiling, median_mbps=filed).mbps
    if reached is None or advertised is None:
        return reached
    # A fast cell does not make a slow plan fast: their 5G router sold at 50 Mbps delivers
    # 50 wherever it stands, and the grid saying 300 is about the cell, not the contract.
    return min(advertised, reached)


def owned(needs_hardware: str | None, hardware_eur: Decimal | None) -> Decimal | None:
    """What the equipment costs, which for most plans is nothing because there is none.

    A plan that names no equipment has none to pay for, so zero here is what the catalogue
    says rather than what we assumed it meant. A plan that does name some and quotes no
    price stays unknown, because a dish nobody priced is not a free dish.
    """
    if needs_hardware is None:
        return Decimal(0)
    return hardware_eur


def options(conn: psycopg.Connection[TupleRow], address_id: int) -> list[Option]:
    """Everything buyable here, with a cost and an expectation attached to each."""
    reach = mobile(conn, address_id)
    rows = conn.execute(PLANS, {
        "address": address_id,
        "airtime": AIRTIME,
        "everywhere": list(EVERYWHERE),
    }).fetchall()

    found: list[Option] = []
    for (code, name, technology, family, advertised, needs_hardware, cap, ceiling,
         monthly, setup, hardware, promo_months, promo_monthly,
         quoted, filed) in rows:
        here = filed
        if technology == AIRTIME:
            # Airtime is only worth anything where the operator's own network reaches, and
            # the grid is the only thing that knows whether it does.
            covers = reach.get(str(code))
            if covers is None:
                continue
            here = covers.floor_mbps
        found.append(Option(
            provider=str(code),
            plan=str(name),
            technology=str(technology),
            family=str(family),
            expected_mbps=speed(str(family), advertised, ceiling, quoted, here),
            data_cap_gb=cap,
            cost=blended(Price(
                monthly_eur=monthly,
                setup_eur=setup,
                hardware_eur=owned(needs_hardware, hardware),
                promo_months=promo_months,
                promo_monthly_eur=promo_monthly,
            )),
        ))
    return found
