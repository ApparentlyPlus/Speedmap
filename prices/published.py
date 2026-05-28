"""Tariffs from providers that publish no catalogue an adapter can read.

Vodafone answers with JSON and Nova quotes with an eligibility check, so both are fetched.
The rest publish a web page or a PDF, and a scraper over either breaks on a stylesheet
change without saying so. These are read once by hand, recorded against the page they came
from and the day they were read, and reviewed like any other change.

One provider is missing on purpose. ΔΕΗ's own rate card asks 60€ for a gigabit while the
market reports it selling near 20€, and their order portal quotes only after an address
check, so the retail price has no primary source. The rate card is recorded as published:
it is what they say the plan costs, and inventing the difference would be worse.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml

from prices.catalogue import Tariff

PUBLISHED = Path(__file__).parent / "published.yaml"

# Which family a technology belongs to, so a plan lands in the same vocabulary as coverage.
FAMILY = {
    "FTTH": "fibre",
    "DOCSIS": "coax",
    "VECT_VDSL": "copper",
    "VDSL": "copper",
    "ADSL": "copper",
    "FWA_4G": "wireless",
    "FWA_5G": "wireless",
    "FWA": "wireless",
    "SAT": "satellite",
}


def money(value: object) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def tariff(plan: dict[str, Any]) -> Tariff:
    technology = str(plan["technology"])
    return Tariff(
        external_key=str(plan["key"]),
        name=str(plan["name"]),
        family=FAMILY[technology],
        technology=technology,
        down_mbps=money(plan.get("down_mbps")),
        up_mbps=money(plan.get("up_mbps")),
        monthly_eur=Decimal(str(plan["monthly_eur"])),
        setup_eur=money(plan.get("setup_eur")),
        hardware_eur=money(plan.get("hardware_eur")),
        contract_months=plan.get("contract_months"),
        promo_months=plan.get("promo_months"),
        promo_monthly_eur=money(plan.get("promo_monthly_eur")),
    )


def load(path: Path = PUBLISHED) -> dict[str, tuple[list[Tariff], date]]:
    """Every recorded catalogue, by provider, with the day it was read."""
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    found: dict[str, tuple[list[Tariff], date]] = {}
    for provider, entry in document.items():
        plans = [tariff(plan) for plan in entry["plans"]]
        found[str(provider)] = (plans, entry["observed_on"])
    return found
