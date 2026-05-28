"""What a provider sells, and what it charged on the day we looked.

A plan is what it is; a price is what it was. The two are separated because a tariff changes
under a plan that does not, and a comparison made last month has to stay answerable.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import psycopg
from psycopg.rows import TupleRow

PLAN = """
insert into plan (
    provider_id, external_key, name, family, technology, down_mbps, up_mbps, needs_hardware
)
select p.id, %(key)s, %(name)s, %(family)s, %(technology)s, %(down)s, %(up)s, %(hardware)s
from provider p where p.code = %(provider)s
on conflict (provider_id, external_key) do update set
    name = excluded.name,
    family = excluded.family,
    technology = excluded.technology,
    down_mbps = excluded.down_mbps,
    up_mbps = excluded.up_mbps,
    needs_hardware = excluded.needs_hardware
returning id
"""

PRICE = """
insert into plan_price (
    plan_id, observed_on, monthly_eur, setup_eur, hardware_eur,
    contract_months, promo_months, promo_monthly_eur
)
values (
    %(plan)s, %(on)s, %(monthly)s, %(setup)s, %(hardware)s,
    %(contract)s, %(promo_months)s, %(promo_monthly)s
)
on conflict (plan_id, observed_on) do update set
    monthly_eur = excluded.monthly_eur,
    setup_eur = excluded.setup_eur,
    hardware_eur = excluded.hardware_eur,
    contract_months = excluded.contract_months,
    promo_months = excluded.promo_months,
    promo_monthly_eur = excluded.promo_monthly_eur
"""


@dataclass(frozen=True)
class Tariff:
    """One plan as a provider advertises it today.

    None is not zero anywhere here. A catalogue that does not mention a setup fee has not
    said there isn't one, and the ranker refuses to blend a cost it was never told.
    """

    external_key: str
    name: str
    family: str
    monthly_eur: Decimal
    technology: str | None = None
    down_mbps: Decimal | None = None
    up_mbps: Decimal | None = None
    needs_hardware: str | None = None
    setup_eur: Decimal | None = None
    hardware_eur: Decimal | None = None
    contract_months: int | None = None
    promo_months: int | None = None
    promo_monthly_eur: Decimal | None = None


def write(
    conn: psycopg.Connection[TupleRow],
    provider: str,
    tariffs: list[Tariff],
    observed_on: date,
) -> int:
    """Record today's catalogue. Rerunning on the same day corrects it rather than doubling."""
    written = 0
    for tariff in tariffs:
        row = conn.execute(PLAN, {
            "provider": provider,
            "key": tariff.external_key,
            "name": tariff.name,
            "family": tariff.family,
            "technology": tariff.technology,
            "down": tariff.down_mbps,
            "up": tariff.up_mbps,
            "hardware": tariff.needs_hardware,
        }).fetchone()
        if row is None:
            continue
        conn.execute(PRICE, {
            "plan": row[0],
            "on": observed_on,
            "monthly": tariff.monthly_eur,
            "setup": tariff.setup_eur,
            "hardware": tariff.hardware_eur,
            "contract": tariff.contract_months,
            "promo_months": tariff.promo_months,
            "promo_monthly": tariff.promo_monthly_eur,
        })
        written += 1
    return written
