"""Tariffs recorded by hand from published.yaml, for providers with no readable catalogue."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml

from prices.catalogue import Tariff

PUBLISHED = Path(__file__).parent / "published.yaml"

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
    """(provider, plans, day read) per page."""
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [
        (str(entry.get("provider", name)), [tariff(p) for p in entry["plans"]], entry["observed_on"])
        for name, entry in doc.items()
    ]


def load(path: Path = PUBLISHED) -> dict[str, tuple[list[Tariff], date]]:
    """Plans by provider, with the latest day any of its pages was read."""
    found: dict[str, tuple[list[Tariff], date]] = {}
    for provider, plans, day in sections(path):
        held, seen = found.get(provider, ([], day))
        found[provider] = (held + plans, max(seen, day))
    return found
