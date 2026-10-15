"""Vodafone's fixed catalogue, one request for every residential plan."""

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

# same codes the availability check answers in
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

HARDWARE = {"FWA_4G": "5g_router", "FWA_5G": "5g_router"}

# from the plan pages, the payload leaves it out
ACTIVATION = {"fiber": Decimal(6), "copper": Decimal(6), "wireless": Decimal(40)}


class CatalogueError(RuntimeError):
    pass


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
    """(sale, list) price."""
    found: dict[str, Decimal] = {}
    entries = offering.get("productOfferingPrice")
    for entry in entries if isinstance(entries, list) else []:
        if not isinstance(entry, dict):
            continue
        price = entry.get("price")
        price = price if isinstance(price, dict) else {}
        tax = price.get("taxIncludedAmount")
        tax = tax if isinstance(tax, dict) else {}
        v = euros(tax.get("value"))
        if v is not None:
            found[str(entry.get("name"))] = v
    return found.get("salePrice"), found.get("initialPrice")


def read(payload: dict[str, Any]) -> list[Tariff]:
    tariffs: list[Tariff] = []
    subs = payload.get("subCategory")
    for sub in subs if isinstance(subs, list) else []:
        if not isinstance(sub, dict):
            continue
        offerings = sub.get("productOffering")
        for offering in offerings if isinstance(offerings, list) else []:
            if not isinstance(offering, dict):
                continue
            # unknown codes are skipped, a guess could match the wrong line
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
                monthly_eur=listed if discount is not None and listed is not None else sale,  # what it reverts to
                setup_eur=ACTIVATION.get(family),
                hardware_eur=Decimal(0),  # router included
                promo_monthly_eur=discount,
                # promo_months unknown, so the blend charges list price throughout
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
        r = client.post(f"/api/proxy-request{CATALOGUE}", json={
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

    if r.status_code != httpx.codes.OK:
        raise CatalogueError(f"catalogue returned {r.status_code}")
    body = r.json()
    payload = body.get("response") if isinstance(body, dict) else None
    if not isinstance(payload, dict):
        raise CatalogueError("catalogue returned no offerings")
    return read(payload)
