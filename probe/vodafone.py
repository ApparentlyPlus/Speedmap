"""Ask Vodafone what it will sell at a set of coordinates.

Alone among the three retail operators this one is keyed on a point rather than on its own
spelling of a street, so it needs no crosswalk: the register already placed 99.94% of the
country. Their own onboarding flow geocodes a typed address first, which is a step we can
skip entirely.

The endpoint is a TM Forum service qualification behind a same-origin proxy, so the real
request travels as a payload and the session cookie from the onboarding page is required.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx
import psycopg
from psycopg.rows import TupleRow

from db.settings import settings
from probe.adapter import Offer, Probed, Target

BASE = "https://www.vodafone.gr"
ONBOARDING = f"{BASE}/fixed-onboarding?persistState=true"
QUALIFY = "/tmf-api/serviceQualificationManagement/v4/queryServiceQualification"

# Their identifier for a retail consumer, as their own onboarding sends it.
RETAIL_PARTY = "1-DIUSAOI90"

# What they call a technology, in our vocabulary. A hundred megabits over copper is
# vectored by definition, which is why the two VDSL rungs do not map to one code.
TECHNOLOGY = {
    "ADSL": "ADSL",
    "VDSL_50": "VDSL",
    "VDSL_100": "VECT_VDSL",
    "FTTH_100": "FTTH",
    "FTTH_300": "FTTH",
    "FTTH_500": "FTTH",
    "FTTH_1000": "FTTH",
}

# Categories that qualify without naming a service to go with it. Fixed wireless answers
# that it reaches here and quotes nothing, and the generation is not said, so the offer
# stays generic rather than claiming a 5G it never mentioned.
BARE_CATEGORY = {"FWA": "FWA"}


class ProbeError(RuntimeError):
    """The checker could not be asked. Not an answer, and never cached as one."""


def mbps(value: object) -> Decimal | None:
    """A promised speed, or None when the operator quoted nothing usable."""
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def characteristics(entries: object) -> dict[str, object]:
    if not isinstance(entries, list):
        return {}
    return {
        str(e.get("name")): e.get("value")
        for e in entries
        if isinstance(e, dict) and e.get("name") is not None
    }


def offers(payload: dict[str, Any]) -> tuple[Offer, ...]:
    """Every technology the answer qualifies, in our vocabulary.

    A category we have no code for is dropped rather than guessed: their IPTV is not
    broadband, and a technology they add later is a change we should notice, not absorb.
    """
    found: dict[str, Offer] = {}
    items = payload.get("serviceQualificationItem")
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        service = item.get("service")
        service = service if isinstance(service, dict) else {}

        named = False
        supporting = service.get("supportingService")
        for entry in supporting if isinstance(supporting, list) else []:
            if not isinstance(entry, dict):
                continue
            technology = TECHNOLOGY.get(str(entry.get("name")))
            if technology is None:
                continue
            named = True
            spec = characteristics(entry.get("serviceCharacteristic"))
            found[technology] = Offer(
                technology=technology,
                max_down_mbps=mbps(spec.get("maxPromisedSpeedDownload")),
                avg_down_mbps=mbps(spec.get("averagePromisedSpeedDownload")),
                avg_up_mbps=mbps(spec.get("averagePromisedSpeedUpload")),
            )

        if named:
            continue
        category = item.get("category")
        category = category if isinstance(category, dict) else {}
        bare = BARE_CATEGORY.get(str(category.get("name")))
        if bare is not None and bare not in found:
            found[bare] = Offer(technology=bare)

    return tuple(found[code] for code in sorted(found))


def cabinet(payload: dict[str, Any]) -> dict[str, object]:
    """The exchange and street cabinet the line hangs off, which is why copper varies."""
    items = payload.get("serviceQualificationItem")
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        service = item.get("service")
        service = service if isinstance(service, dict) else {}
        resources = service.get("supportingResource")
        for resource in resources if isinstance(resources, list) else []:
            if isinstance(resource, dict) and resource.get("category") == "DSLAM":
                spec = characteristics(resource.get("resourceCharacteristic"))
                return {"dslam": spec.get("name"), "kvid": spec.get("kvid")}
    return {}


def read(payload: dict[str, Any]) -> Probed:
    """The answer, parsed. Pure, so the shape is tested without asking anyone."""
    found = offers(payload)
    return Probed(
        serviceable=bool(found),
        offers=found,
        raw={"cabinet": cabinet(payload), "technologies": [o.technology for o in found]},
    )


@dataclass
class Vodafone:
    """A session against their onboarding flow, reused across checks."""

    code: str = "VODAFONE"
    client: httpx.Client | None = None
    user_agent: str = settings.user_agent

    def session(self) -> httpx.Client:
        if self.client is not None:
            return self.client
        client = httpx.Client(
            base_url=BASE,
            timeout=30.0,
            headers={
                "User-Agent": self.user_agent,
                "Accept-Language": "el",
                "Accept": "application/json, text/plain, */*",
                "Content-Type": "application/json",
                "Origin": BASE,
                "Referer": ONBOARDING,
                "sec-fetch-mode": "cors",
                "sec-fetch-site": "same-origin",
            },
        )
        # The proxy will not act without the cookie the onboarding page sets.
        client.get(ONBOARDING, headers={"Accept": "text/html"})
        self.client = client
        return client

    def request(self, target: Target) -> dict[str, object]:
        return {
            "method": "POST",
            "headers": {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "vf-country-code": "GR",
                "x-vf-api-process": "CELL",
            },
            "endpoint": QUALIFY,
            "data": {
                "instantSyncQualification": "true",
                "@type": "QueryServiceQualification",
                "searchCriteria": {
                    "id": "1",
                    "@type": "ServiceQualificationItem",
                    "service": {
                        "place": [{
                            "role": "Installation Place",
                            "@type": "GeographicAddressExtended",
                            "geographicLocation": {
                                "bbox": [target.lat, target.lon],
                                "@type": "GeoJsonPoint",
                            },
                        }],
                        "relatedParty": [{
                            "id": RETAIL_PARTY,
                            "@type": "RelatedPartyExtended",
                            "@baseType": "RelatedParty",
                            "@referredType": "Individual",
                            "role": "CustomerType",
                            "name": "Retail",
                        }],
                    },
                },
            },
            "isServerToken": True,
            "requestId": f"speedmap-{target.address_id}",
        }

    def check(self, conn: psycopg.Connection[TupleRow], target: Target) -> Probed:
        """The connection is unused: a point is the whole query, which is the point of it."""
        response = self.session().post(
            f"/api/proxy-request{QUALIFY}", json=self.request(target)
        )
        if response.status_code != httpx.codes.OK:
            raise ProbeError(f"qualification returned {response.status_code}")
        body = response.json()
        payload = body.get("response") if isinstance(body, dict) else None
        if not isinstance(payload, dict):
            raise ProbeError("qualification returned no answer")
        probed = read(payload)
        return replace(probed, body=response.text)
