"""Vodafone's fixed catalogue, which they publish whole.

One request returns every residential fixed plan with its price and the qualification code the
availability check answers in.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from db.settings import settings
from prices.catalogue import Tariff

BASE = "https://www.vodafone.gr"
ONBOARDING = f"{BASE}/fixed-onboarding?persistState=true"
CATALOGUE = (
    "/productSelector/v2/mainProductOffering"
    "?expand=productSpecification,category"
    "&name=TARIFF_PLAN"
    "&subcategory.productOffering.productSpecification.name=Fixed"
)

# Their qualification code, in our vocabulary. The same codes come back from the
# availability check, which is what lets a plan be matched to a line.
TECHNOLOGY = {
    "ADSL": ("ADSL", "copper", 24),
    "VDSL_50": ("VDSL", "copper", 50),
    "VDSL_100": ("VECT_VDSL", "copper", 100),
    "FTTH_100": ("FTTH", "fibre", 100),
    "FTTH_300": ("FTTH", "fibre", 300),
    "FTTH_500": ("FTTH", "fibre", 500),
    "FTTH_1000": ("FTTH", "fibre", 1000),
    "FWA 4G": ("FWA_4G", "wireless", None),
    "FWA 5G": ("FWA_5G", "wireless", None),
}

# A home router is part of the offer, not an optional extra, and it is a real cost.
HARDWARE = {"FWA_4G": "5g_router", "FWA_5G": "5g_router"}

# Their plan pages state an activation fee that the catalogue payload leaves out entirely.
ACTIVATION = {"fibre": Decimal(6), "copper": Decimal(6), "wireless": Decimal(40)}


class CatalogueError(RuntimeError):
    """The catalogue could not be read."""


def euros(value: object) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def identifier(offering: dict[str, Any], kind: str) -> str | None:
    spec = offering.get("productSpecification")
    spec = spec if isinstance(spec, dict) else {}
    entries = spec.get("externalIdentifier")
    for entry in entries if isinstance(entries, list) else []:
        if isinstance(entry, dict) and entry.get("externalIdentifierType") == kind:
            return None if entry.get("id") is None else str(entry["id"])
    return None


def priced(offering: dict[str, Any]) -> tuple[Decimal | None, Decimal | None]:
    """The sale price and the list price it is struck from, when they differ."""
    found: dict[str, Decimal] = {}
    entries = offering.get("productOfferingPrice")
    for entry in entries if isinstance(entries, list) else []:
        if not isinstance(entry, dict):
            continue
        amount = entry.get("price")
        amount = amount if isinstance(amount, dict) else {}
        tax = amount.get("taxIncludedAmount")
        tax = tax if isinstance(tax, dict) else {}
        value = euros(tax.get("value"))
        if value is not None:
            found[str(entry.get("name"))] = value
    return found.get("salePrice"), found.get("initialPrice")


def read(payload: dict[str, Any]) -> list[Tariff]:
    """Every fixed plan they publish, in our vocabulary.

    A plan whose code we do not know is skipped rather than filed under a guess: it would be
    shown against a line it may not run on.
    """
    tariffs: list[Tariff] = []
    subcategories = payload.get("subCategory")
    for subcategory in subcategories if isinstance(subcategories, list) else []:
        if not isinstance(subcategory, dict):
            continue
        offerings = subcategory.get("productOffering")
        for offering in offerings if isinstance(offerings, list) else []:
            if not isinstance(offering, dict):
                continue
            code = identifier(offering, "AvToolCode")
            known = TECHNOLOGY.get(str(code))
            sale, listed = priced(offering)
            if known is None or sale is None:
                continue
            technology, family, mbps = known
            key = identifier(offering, "TariffPlanCode")
            tariffs.append(Tariff(
                external_key=key if key is not None else str(offering.get("name")),
                name=str(offering.get("name")),
                family=family,
                technology=technology,
                down_mbps=None if mbps is None else Decimal(mbps),
                needs_hardware=HARDWARE.get(technology),
                monthly_eur=sale,
                setup_eur=ACTIVATION.get(family),
                # They give the router with the plan and charge nothing for it.
                hardware_eur=Decimal(0),
                # Equal prices mean no discount is running, not a discount of nothing.
                promo_monthly_eur=None if listed is None or listed == sale else sale,
            ))
    return tariffs


def fetch(user_agent: str = settings.user_agent) -> list[Tariff]:
    with httpx.Client(base_url=BASE, timeout=30.0, headers={
        "User-Agent": user_agent,
        "Accept-Language": "el",
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Origin": BASE,
        "Referer": ONBOARDING,
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
    }) as client:
        client.get(ONBOARDING, headers={"Accept": "text/html"})
        response = client.post(f"/api/proxy-request{CATALOGUE}", json={
            "method": "GET",
            "headers": {
                "Accept": "application/json",
                "vf-country-code": "GR",
                "x-vf-api-process": "fixedActivation",
            },
            "endpoint": CATALOGUE,
            "isServerToken": True,
            "requestId": "speedmap-catalogue",
        })
    if response.status_code != httpx.codes.OK:
        raise CatalogueError(f"catalogue returned {response.status_code}")
    body = response.json()
    payload = body.get("response") if isinstance(body, dict) else None
    if not isinstance(payload, dict):
        raise CatalogueError("catalogue returned no offerings")
    return read(payload)
