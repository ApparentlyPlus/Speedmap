"""Everything buyable at one address, priced, with an expected speed.

Three kinds of plan qualify differently. A line qualifies when the operator files coverage
here or its checker said yes. Airtime qualifies where the operator's mobile grid reaches.
Satellite qualifies everywhere.
"""

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

# sold anywhere there's sky, so coverage never filters it out
EVERYWHERE = frozenset({"satellite"})

# airtime pointed at a router, so the mobile grid is what qualifies it
AIRTIME = "MOBILE"

PLANS = """
-- each operator's last scrape date, computed once instead of per plan row
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
-- Vodafone's checker says fixed wireless reaches here but never which generation, so the
-- answer is stored as FWA while the plans are FWA_4G and FWA_5G. Matched on code alone, a
-- yes never unlocked a single wireless plan. An exact code match wins when both exist.
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
  -- A plan missing from its operator's latest scrape was withdrawn. Its last price stays in
  -- plan_price as history, and was being offered as current forever. Scraped catalogues only,
  -- since hand-recorded pages are dated a section at a time.
  and (pc.source <> 'catalogue' or pc.observed_on >= scraped.latest)
"""


@dataclass(frozen=True)
class Reckoned:
    """A speed and where it came from."""

    mbps: Decimal | None
    basis: str
    confidence: float = 0.0
    tests: int = 0


def capped(reached: Decimal | None, advertised: Decimal | None) -> Decimal | None:
    """A fast street doesn't make a slow plan fast.

    A 5G router sold at 50 Mbps delivers 50 wherever it sits. A tile measuring 260 is about the
    cell, and the contract still says 50.
    """
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
    """What this offer should deliver here, and on what evidence.

    Three kinds, most specific to this address first: an operator quote, a measurement, the filing.
    """
    if quote is not None:
        return Reckoned(capped(quote, advertised), basis="quoted")

    if measured is not None:
        speed_of = expected(
            family, advertised, ceiling,
            median_mbps=measured.down_mbps, tests=measured.tests, filed_mbps=filed,
        )
        # only call it measured when a measurement was used
        if speed_of.mbps is not None and speed_of.measured:
            # A tile mixes every operator in it. One filing a slower band here is saying its
            # own mast is worse than the area, and it would know.
            held = capped(speed_of.mbps, ceiling_here)
            return Reckoned(
                capped(held, advertised), basis="measured",
                confidence=speed_of.confidence, tests=measured.tests,
            )

    speed_of = expected(family, advertised, ceiling, median_mbps=filed)
    basis = "filed" if filed is not None else "advertised"
    return Reckoned(capped(capped(speed_of.mbps, ceiling_here), advertised), basis=basis)


def owned(needs_hardware: str | None, hardware_eur: Decimal | None) -> Decimal | None:
    """What the equipment costs, nothing for most plans because there isn't any.

    A plan naming no equipment has none to pay for, so this zero comes from the catalogue.
    """
    if needs_hardware is None:
        return Decimal(0)
    return hardware_eur


def options(conn: psycopg.Connection[TupleRow], address_id: int) -> list[Option]:
    """Everything buyable here, each with a cost and an expected speed."""
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

    options_out: list[Option] = []
    for (code, shown, name, technology, family, advertised, needs_hardware, cap, ceiling,
         monthly, setup, hardware, promo_months, promo_monthly,
         quote, filed, held_to) in rows:
        here = filed
        # A line filed as normally carrying less than the plan's speed delivers that less, as
        # the map already shows: the street is painted at the cap, and this card was promising
        # the plan's full figure on the same line. Fixed lines only.
        ceiling_here = held_to if str(family) not in ("wireless", "satellite") else None
        if technology == AIRTIME:
            # airtime is worthless where the operator's own network doesn't reach, and only the
            # grid knows where it does
            covers = reach.get(str(code))
            if covers is None:
                continue
            here = covers.floor_mbps
            ceiling_here = covers.ceiling_mbps
        speed_of = speed(
            str(family), advertised, ceiling, quote, here,
            for_family(tested, str(family)), ceiling_here,
        )
        options_out.append(Option(
            provider=str(code),
            provider_name=str(shown),
            plan=str(name),
            technology=str(technology),
            family=str(family),
            expected_mbps=speed_of.mbps,
            data_cap_gb=cap,
            basis=speed_of.basis,
            confidence=speed_of.confidence,
            tests=speed_of.tests,
            cost=blended(Price(
                monthly_eur=monthly,
                setup_eur=setup,
                hardware_eur=owned(needs_hardware, hardware),
                promo_months=promo_months,
                promo_monthly_eur=promo_monthly,
            )),
        ))
    return options_out
