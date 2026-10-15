"""Everything buyable at one address, priced, with an expected speed."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import psycopg
from psycopg.rows import TupleRow

from ranking.cost import Price, blended
from ranking.grid import mobile
from ranking.measured import Measured, for_family, nearby
from ranking.rank import Option
from ranking.speed import expected

# lines need filed coverage or a yes, airtime the mobile grid, satellite nothing
EVERYWHERE = frozenset({"satellite"})
AIRTIME = "MOBILE"  # a data plan in a router

PLANS = """
with scraped as (
    select other.provider_id, max(pp.observed_on) as latest
    from plan_price pp
    join plan other on other.id = pp.plan_id
    where pp.source = 'catalogue'
    group by other.provider_id
)
select pr.code, pr.display_name, pl.name, pl.technology, pl.family, pl.down_mbps,
       pl.needs_hardware, pl.data_cap_gb, t.max_plausible_mbps,
       pc.monthly_eur, pc.setup_eur, pc.hardware_eur,
       pc.promo_months, pc.promo_monthly_eur,
       v.avg_down_mbps,
       sb.min_mbps,
       coalesce(nb.max_mbps, sb.max_mbps)
from plan pl
join provider pr on pr.id = pl.provider_id
join plan_current pc on pc.plan_id = pl.id
join technology t on t.code = pl.technology
-- Vodafone answers FWA but sells FWA_4G/FWA_5G, exact match first
left join lateral (
    select v.address_id, v.avg_down_mbps
    from availability v
    where v.address_id = %(address)s and v.provider_id = pl.provider_id and v.serviceable
      and (v.technology = pl.technology
           or (v.technology = 'FWA' and pl.technology in ('FWA_4G', 'FWA_5G')))
    order by v.technology = pl.technology desc
    limit 1
) v on true
left join address_coverage ac
       on ac.address_id = %(address)s and ac.provider_id = pl.provider_id
      and ac.technology = pl.technology
left join speed_band sb on sb.id = ac.speed_band_id
left join speed_band nb on nb.id = ac.normal_band_id
left join scraped on scraped.provider_id = pl.provider_id
where (pl.technology = %(airtime)s
   or pl.family = any(%(everywhere)s)
   or v.address_id is not null
   or ac.address_id is not null)
  -- missing from the latest scrape means withdrawn (hand recorded pages are dated per section)
  and (pc.source <> 'catalogue' or pc.observed_on >= scraped.latest)
"""


@dataclass(frozen=True)
class Reckoned:
    mbps: Decimal | None
    basis: str
    confidence: float = 0.0
    tests: int = 0


def capped(reached: Decimal | None, advertised: Decimal | None) -> Decimal | None:
    # a 50 Mbps 5G plan stays 50 in a tile that measures 260
    if reached is None or advertised is None:
        return reached
    return min(advertised, reached)


def speed(
    family: str,
    advertised: Decimal | None,
    ceiling: Decimal | None,
    quote: Decimal | None,
    filed: Decimal | None,
    measured: Measured | None,
    ceiling_here: Decimal | None = None,
) -> Reckoned:
    # most specific first: operator quote, measurement, filing
    if quote is not None:
        return Reckoned(capped(quote, advertised), basis="quoted")

    if measured is not None:
        e = expected(family, advertised, ceiling, median_mbps=measured.down_mbps,
                     tests=measured.tests, filed_mbps=filed)
        if e.mbps is not None and e.measured:
            # the tile mixes operators, one filing a slower band here knows its own mast
            held = capped(e.mbps, ceiling_here)
            return Reckoned(capped(held, advertised), basis="measured", confidence=e.confidence, tests=measured.tests)

    e = expected(family, advertised, ceiling, median_mbps=filed)
    basis = "filed" if filed is not None else "advertised"
    return Reckoned(capped(capped(e.mbps, ceiling_here), advertised), basis=basis)


def owned(needs_hardware: str | None, hardware_eur: Decimal | None) -> Decimal | None:
    if needs_hardware is None:
        return Decimal(0)
    return hardware_eur


def options(conn: psycopg.Connection[TupleRow], address_id: int) -> list[Option]:
    reach = mobile(conn, address_id)
    point = conn.execute(
        "select st_y(geom::geometry), st_x(geom::geometry) from address where id = %s",
        (address_id,),
    ).fetchone()
    tested = {} if point is None else nearby(conn, float(point[0]), float(point[1]))
    rows = conn.execute(PLANS, {
        "address": address_id,
        "airtime": AIRTIME,
        "everywhere": list(EVERYWHERE),
    }).fetchall()

    out: list[Option] = []
    for (code, shown, name, technology, family, advertised, needs_hardware, cap, ceiling,
         monthly, setup, hardware, promo_months, promo_monthly,
         quote, filed, held_to) in rows:
        here = filed
        # fixed lines filed as normally carrying less get capped, like the map paints them
        ceiling_here = held_to if str(family) not in ("wireless", "satellite") else None
        if technology == AIRTIME:
            covers = reach.get(str(code))
            if covers is None:
                continue
            here = covers.floor_mbps
            ceiling_here = covers.ceiling_mbps
        s = speed(str(family), advertised, ceiling, quote, here, for_family(tested, str(family)), ceiling_here)
        out.append(Option(
            provider=str(code),
            provider_name=str(shown),
            plan=str(name),
            technology=str(technology),
            family=str(family),
            expected_mbps=s.mbps,
            data_cap_gb=cap,
            basis=s.basis,
            confidence=s.confidence,
            tests=s.tests,
            cost=blended(Price(
                monthly_eur=monthly,
                setup_eur=setup,
                hardware_eur=owned(needs_hardware, hardware),
                promo_months=promo_months,
                promo_monthly_eur=promo_monthly,
            )),
        ))
    return out
