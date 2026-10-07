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

# Their qualification codes in our vocabulary. The availability check answers in the same
# codes, which is how a plan gets matched to a line.
TECHNOLOGY = {
    "ADSL": ("ADSL", "copper", 24),
    "VDSL_50": ("VDSL", "copper", 50),
    "VDSL_100": ("VECT_VDSL", "copper", 100),
    "FTTH_100": ("FTTH", "fiber", 100),
    "FTTH_300": ("FTTH", "fiber", 300),
    "FTTH_500": ("FTTH", "fiber", 500),
    "FTTH_1000": ("FTTH", "fiber", 1000),
    "FWA 4G": ("FWA_4G", "wireless", None),
    "FWA 5G": ("FWA_5G", "wireless", None),
}

# the home router comes with the offer and is a real cost
HARDWARE = {"FWA_4G": "5g_router", "FWA_5G": "5g_router"}

# their plan pages state an activation fee the catalogue payload leaves out
ACTIVATION = {"fiber": Decimal(6), "copper": Decimal(6), "wireless": Decimal(40)}


class CatalogueError(RuntimeError):
    """The catalogue couldn't be read."""


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
    """The sale price, and the list price it's marked down from."""
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

    A plan with an unknown code is skipped. Filed under a guess, it would show against a line
    it may not run on.
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
            # equal prices mean no discount running
            discount = None if listed is None or listed == sale else sale
            key = identifier(offering, "TariffPlanCode")
            tariffs.append(Tariff(
                external_key=key if key is not None else str(offering.get("name")),
                name=str(offering.get("name")),
                family=family,
                technology=technology,
                down_mbps=None if mbps is None else Decimal(mbps),
                needs_hardware=HARDWARE.get(technology),
                # The price it reverts to. Both used to be stored as the sale price, losing the
                # list price and treating a discount as permanent.
                monthly_eur=listed if discount is not None and listed is not None else sale,
                setup_eur=ACTIVATION.get(family),
                # the router is included at no charge
                hardware_eur=Decimal(0),
                promo_monthly_eur=discount,
                # The feed never says how long a discount lasts. Unknown stays None, so the blend
                # charges the list price for the whole window: a floor on the saving, with no
                # months of discount invented.
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
