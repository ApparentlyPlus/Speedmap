"""Plans and their prices by day. Kept apart so last month's prices stay answerable."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import psycopg
from psycopg.rows import TupleRow

PLAN = """
insert into plan (
    provider_id, external_key, name, family, technology,
    down_mbps, up_mbps, data_cap_gb, needs_hardware
)
select p.id, %(key)s, %(name)s, %(family)s, %(technology)s,
       %(down)s, %(up)s, %(cap)s, %(hardware)s
from provider p where p.code = %(provider)s
on conflict (provider_id, external_key) do update set
    data_cap_gb = excluded.data_cap_gb,
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
    contract_months, promo_months, promo_monthly_eur, source
)
values (
    %(plan)s, %(on)s, %(monthly)s, %(setup)s, %(hardware)s,
    %(contract)s, %(promo_months)s, %(promo_monthly)s, %(source)s
)
on conflict (plan_id, observed_on) do update set
    source = excluded.source,
    monthly_eur = excluded.monthly_eur,
    setup_eur = excluded.setup_eur,
    hardware_eur = excluded.hardware_eur,
    contract_months = excluded.contract_months,
    promo_months = excluded.promo_months,
    promo_monthly_eur = excluded.promo_monthly_eur
"""


@dataclass(frozen=True)
class Tariff:
    # None is unknown, never zero
    external_key: str
    name: str
    family: str
    monthly_eur: Decimal
    technology: str | None = None
    down_mbps: Decimal | None = None
    up_mbps: Decimal | None = None
    data_cap_gb: int | None = None
    needs_hardware: str | None = None
    setup_eur: Decimal | None = None
    hardware_eur: Decimal | None = None
    contract_months: int | None = None
    promo_months: int | None = None
    promo_monthly_eur: Decimal | None = None


def write(conn: psycopg.Connection[TupleRow], provider: str, tariffs: list[Tariff], observed_on: date,
          source: str = "catalogue") -> int:
    """A rerun the same day overwrites. source is "catalogue" or "published" (a rate card)."""
    n = 0
    for t in tariffs:
        row = conn.execute(PLAN, {
            "provider": provider,
            "key": t.external_key,
            "name": t.name,
            "family": t.family,
            "technology": t.technology,
            "down": t.down_mbps,
            "up": t.up_mbps,
            "cap": t.data_cap_gb,
            "hardware": t.needs_hardware,
        }).fetchone()
        if row is None:
            continue
        conn.execute(PRICE, {
            "plan": row[0],
            "on": observed_on,
            "monthly": t.monthly_eur,
            "setup": t.setup_eur,
            "hardware": t.hardware_eur,
            "contract": t.contract_months,
            "promo_months": t.promo_months,
            "promo_monthly": t.promo_monthly_eur,
            "source": source,
        })
        n += 1
    return n
