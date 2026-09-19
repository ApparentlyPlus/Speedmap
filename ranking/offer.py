"""Assemble what is actually buyable at one address, priced and speed-tempered.

Three kinds of thing end up here and they qualify differently. A line qualifies because the
operator files coverage at this address.
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

# Sold from everywhere there is sky, so it is never filtered out by coverage.
EVERYWHERE = frozenset({"satellite"})

# Bought as airtime and pointed at a router, so what qualifies it is the mobile grid.
AIRTIME = "MOBILE"

PLANS = """
select pr.code, pr.display_name, pl.name, pl.technology, pl.family, pl.down_mbps,
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


@dataclass(frozen=True)
class Reckoned:
    """A speed and where it came from."""

    mbps: Decimal | None
    basis: str
    confidence: float = 0.0
    tests: int = 0


def capped(reached: Decimal | None, advertised: Decimal | None) -> Decimal | None:
    """A fast street does not make a slow plan fast.

    Their 5G router sold at 50 Mbps delivers 50 wherever it stands, and a tile measuring 260
    is about the cell rather than the contract.
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
    """What this offer should be expected to deliver here, and on what grounds.

    Three kinds of evidence, in order of how specific they are to this address.
    """
    if quote is not None:
        return Reckoned(capped(quote, advertised), basis="quoted")

    if measured is not None:
        speed_of = expected(
            family, advertised, ceiling,
            median_mbps=measured.down_mbps, tests=measured.tests, filed_mbps=filed,
        )
        # Only claim a measurement where one was used.
        if speed_of.mbps is not None and speed_of.measured:
            # A tile is every operator in it at once. One operator filing a slower band
            # here is saying its own mast is worse than the place, and it knows.
            held = capped(speed_of.mbps, ceiling_here)
            return Reckoned(
                capped(held, advertised), basis="measured",
                confidence=speed_of.confidence, tests=measured.tests,
            )

    speed_of = expected(family, advertised, ceiling, median_mbps=filed)
    basis = "filed" if filed is not None else "advertised"
    return Reckoned(capped(speed_of.mbps, advertised), basis=basis)


def owned(needs_hardware: str | None, hardware_eur: Decimal | None) -> Decimal | None:
    """What the equipment costs, which for most plans is nothing because there is none.

    A plan that names no equipment has none to pay for, so zero here is what the catalogue
    says rather than what we assumed it meant.
    """
    if needs_hardware is None:
        return Decimal(0)
    return hardware_eur


def options(conn: psycopg.Connection[TupleRow], address_id: int) -> list[Option]:
    """Everything buyable here, with a cost and an expectation attached to each."""
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
         quote, filed) in rows:
        here = filed
        ceiling_here = None
        if technology == AIRTIME:
            # Airtime is only worth anything where the operator's own network reaches, and
            # the grid is the only thing that knows whether it does.
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
