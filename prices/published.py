"""Tariffs recorded by hand, for providers with no catalogue an adapter can read.

Vodafone answers with JSON and Nova quotes through an eligibility check, so both are fetched.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml

from prices.catalogue import Tariff

PUBLISHED = Path(__file__).parent / "published.yaml"

# technology to family, so a plan lands in the same vocabulary as coverage
FAMILY = {
    "FTTH": "fiber",
    "DOCSIS": "coax",
    "VECT_VDSL": "copper",
    "VDSL": "copper",
    "ADSL": "copper",
    "MOBILE": "wireless",
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
        data_cap_gb=plan.get("data_cap_gb"),
        needs_hardware=plan.get("needs_hardware"),
        monthly_eur=Decimal(str(plan["monthly_eur"])),
        setup_eur=money(plan.get("setup_eur")),
        hardware_eur=money(plan.get("hardware_eur")),
        contract_months=plan.get("contract_months"),
        promo_months=plan.get("promo_months"),
        promo_monthly_eur=money(plan.get("promo_monthly_eur")),
    )


def sections(path: Path = PUBLISHED) -> list[tuple[str, list[Tariff], date]]:
    """Every recorded page: the provider, its plans, and the day that page was read.

    Providers put lines and airtime on different pages, read on different days, so the date
    belongs to the page. Pooled by provider, the first page's date landed on every plan.
    """
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [
        (
            # a section is a page, and names the company when it differs from the section name
            str(entry.get("provider", section)),
            [tariff(plan) for plan in entry["plans"]],
            entry["observed_on"],
        )
        for section, entry in document.items()
    ]


def load(path: Path = PUBLISHED) -> dict[str, tuple[list[Tariff], date]]:
    """Every recorded catalogue by provider, with the latest day it was read."""
    found: dict[str, tuple[list[Tariff], date]] = {}
    for provider, plans, observed_on in sections(path):
        held, seen = found.get(provider, ([], observed_on))
        found[provider] = (held + plans, max(seen, observed_on))
    return found
