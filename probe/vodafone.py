"""Vodafone's checker, the only one that takes a point instead of a street name."""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx
import psycopg
from psycopg.rows import TupleRow

from db.settings import settings
from probe.adapter import Offer, Probed, ProbeError, Target
from probe.descriptor import Descriptor
from probe.walls import refuse

SPEC = Descriptor("VODAFONE")

BASE = SPEC.text("base")
ONBOARDING = SPEC.url("warm")
QUALIFY = SPEC.text("qualify")
PROXY = SPEC.text("proxy")

RETAIL_PARTY = SPEC.text("retail_party")
TECHNOLOGY = SPEC.mapping("technology")

# categories that qualify without naming a service
BARE_CATEGORY = SPEC.mapping("bare")


def mbps(value: object) -> Decimal | None:
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


def faster(offer: Offer, than: Offer) -> bool:
    # any figure beats none
    if offer.max_down_mbps is None:
        return False
    return than.max_down_mbps is None or offer.max_down_mbps > than.max_down_mbps


def offers(payload: dict[str, Any]) -> tuple[Offer, ...]:
    # unknown categories are dropped: IPTV, or something new we'd want to notice
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
            offer = Offer(
                technology=technology,
                max_down_mbps=mbps(spec.get("maxPromisedSpeedDownload")),
                avg_down_mbps=mbps(spec.get("averagePromisedSpeedDownload")),
                avg_up_mbps=mbps(spec.get("averagePromisedSpeedUpload")),
            )
            # four FTTH rungs share a code, keep the fastest
            held = found.get(technology)
            if held is None or faster(offer, held):
                found[technology] = offer

        if named:
            continue
        category = item.get("category")
        category = category if isinstance(category, dict) else {}
        bare = BARE_CATEGORY.get(str(category.get("name")))
        if bare is not None and bare not in found:
            found[bare] = Offer(technology=bare)

    return tuple(found[code] for code in sorted(found))


def cabinet(payload: dict[str, Any]) -> dict[str, object]:
    """The exchange and cabinet, why copper speeds vary."""
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
    found = offers(payload)
    return Probed(
        serviceable=bool(found),
        offers=found,
        raw={"cabinet": cabinet(payload), "technologies": [o.technology for o in found]},
    )


@dataclass
class Vodafone:
    code: str = "VODAFONE"
    client: httpx.Client | None = None
    user_agent: str = settings.user_agent

    def session(self) -> httpx.Client:
        if self.client is not None:
            return self.client
        client = httpx.Client(
            base_url=BASE,
            timeout=30.0,
            event_hooks={"response": [refuse]},
            headers={
                "User-Agent": self.user_agent,
                "Accept": "application/json, text/plain, */*",
                "Content-Type": "application/json",
                "Origin": BASE,
                "Referer": ONBOARDING,
                **SPEC.mapping("headers"),
            },
        )
        # for the cookie, the proxy wants it
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
                "x-vf-api-process": SPEC.text("process"),
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
        r = self.session().post(f"{PROXY}{QUALIFY}", json=self.request(target))
        if r.status_code != httpx.codes.OK:
            raise ProbeError(f"qualification returned {r.status_code}")
        body = r.json()
        payload = body.get("response") if isinstance(body, dict) else None
        if not isinstance(payload, dict):
            raise ProbeError("qualification returned no answer")
        return replace(read(payload), body=r.text)
