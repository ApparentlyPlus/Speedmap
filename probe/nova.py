"""Ask Nova what it will sell at an address.

They want their own spelling, which their address API hands out: a street there is a
(region, municipality, city, street, zipcode) tuple, and a street name repeats across
postcodes, so ours picks which of them is meant. Their region and municipality are the
prefectures and pre-Καλλικράτης municipalities that the other operator uses too.

The answer carries the tariff with it, so an availability check is also a price check.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import quote

import httpx
import psycopg
from psycopg.rows import TupleRow

from db.settings import settings
from probe.adapter import Offer, Probed, Target
from probe.naming import naming

BASE = "https://nova.gr"
LANDING = f"{BASE}/statheri-tilefonia/programmata/stathero-internet"
STREETS = "/api/address/streets"
ELIGIBILITY = "/api/GetEligibilityInfo"

# The entry package their plan page starts every visitor on.
PRESELECTED = {"code": "2P_FIBER_100", "title": "Fiber 100", "price": "29.0"}

# Their code names the speed and nothing else about the medium: 2P_FIBER_100 is vectored
# copper on a copper street and fibre on a fibre one, exactly as the other operator's
# FBR codes are. The rungs are read the same way, from the fastest offered.
RUNGS = ((1000, "FTTH"), (200, "FTTH"), (100, "VECT_VDSL"), (50, "VDSL"), (0, "ADSL"))


class ProbeError(RuntimeError):
    """The checker could not be asked. Not an answer, and never cached as one."""


def speed_of(code: str) -> int | None:
    """The megabits a package code names, or None when it names none."""
    for part in reversed(code.replace("-", "_").split("_")):
        if part.isdigit():
            return int(part)
        if part.endswith("G") and part[:-1].isdigit():
            return int(part[:-1]) * 1000
    return None


def technology_of(mbps: int) -> str:
    for floor, technology in RUNGS:
        if mbps >= floor:
            return technology
    return "ADSL"


def euros(value: object) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value).replace(",", "."))
    except (InvalidOperation, ValueError):
        return None


def read(payload: dict[str, Any]) -> Probed:
    """The answer, parsed. Pure, so the shape is tested without asking anyone."""
    result = payload.get("result")
    result = result if isinstance(result, dict) else {}
    packages = result.get("packages")
    packages = packages if isinstance(packages, list) else []

    best: dict[str, Offer] = {}
    tariffs: list[dict[str, object]] = []
    for package in packages:
        if not isinstance(package, dict):
            continue
        code = str(package.get("code", ""))
        mbps = speed_of(code)
        tariffs.append({
            "code": code,
            "title": package.get("title"),
            "monthly_eur": str(euros(package.get("monthlyFeeDisplay"))),
            "contract_months": package.get("bindPeriod"),
        })
        if mbps is None:
            continue
        technology = technology_of(mbps)
        held = best.get(technology)
        # One technology, many packages at different speeds: keep the fastest of them.
        faster = held is None or held.max_down_mbps is None or held.max_down_mbps < mbps
        if faster:
            best[technology] = Offer(technology=technology, max_down_mbps=Decimal(mbps))

    return Probed(
        serviceable=bool(best),
        offers=tuple(best[code] for code in sorted(best)),
        raw={"address": result.get("formattedAddress"), "packages": tariffs},
    )


@dataclass
class Nova:
    """A session against their plan pages, reused across checks."""

    code: str = "NOVA"
    client: httpx.Client | None = None
    user_agent: str = settings.user_agent
    seen: dict[tuple[str, str], list[dict[str, Any]]] = field(default_factory=dict)

    def session(self) -> httpx.Client:
        if self.client is not None:
            return self.client
        client = httpx.Client(
            base_url=BASE,
            timeout=30.0,
            headers={
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "el",
                "Content-Type": "application/json",
                "User-Agent": self.user_agent,
                "Referer": LANDING,
            },
        )
        client.get(LANDING, headers={"Accept": "text/html"})
        self.client = client
        return client

    def streets(self, region: str, municipality: str, initial: str) -> list[dict[str, Any]]:
        """Their streets under one initial, kept because one call covers a whole town."""
        key = (municipality, initial)
        if key in self.seen:
            return self.seen[key]
        response = self.session().get(
            f"{STREETS}/{quote(initial)}",
            params={"region": region, "municipality": municipality},
        )
        if response.status_code != httpx.codes.OK:
            raise ProbeError(f"street list returned {response.status_code}")
        found = response.json().get("result")
        found = found if isinstance(found, list) else []
        self.seen[key] = found
        return found

    def locate(self, target: Target, region: str, municipality: str) -> dict[str, Any] | None:
        """Which of their street entries this address is, chosen by postcode."""
        name = target.street.upper()
        candidates = [
            s for s in self.streets(region, municipality, name[:1])
            if str(s.get("street", "")).upper() == name
        ]
        if not candidates:
            return None
        # A street name repeats across postcodes, and the wrong one answers about the wrong
        # end of it: ΑΧΑΡΝΩΝ runs through three and only ours says which.
        if target.postcode is not None:
            exact = [s for s in candidates if str(s.get("zipcode")) == target.postcode]
            if exact:
                return exact[0]
        return candidates[0] if len(candidates) == 1 else None

    def check(
        self,
        conn: psycopg.Connection[TupleRow],
        target: Target,
        preselect: Mapping[str, object] | None = None,
    ) -> Probed:
        """Their prefecture and municipality are the same ones the other operator wants,
        with a prefix in front, so one recorded spelling answers for both."""
        named = naming(conn, target.municipality_id, target.street_fold)
        if named is None:
            raise ProbeError(f"no spelling recorded for {target.street}")
        return self.ask(target, named.prefecture, named.municipality, preselect)

    def ask(
        self,
        target: Target,
        region: str,
        municipality: str,
        preselect: Mapping[str, object] | None = None,
    ) -> Probed:
        street = self.locate(target, region, municipality)
        if street is None:
            raise ProbeError(f"no street matched {target.street} in {municipality}")
        payload = {
            # Their own flow arrives here having already chosen a package, and an empty one
            # returns no offers at all. The choice also scopes the answer to that rung and
            # its neighbours, so asking once returns a quarter of what they sell.
            "packagePreselected": PRESELECTED if preselect is None else preselect,
            "packageSelected": {"code": "", "title": "", "price": None, "packageGroupType": ""},
            "customerInfo": {
                "isNewCustomer": True,
                "isExistingCustomerMoving": False,
                "landlineNumber": "",
            },
            "address": {
                "region": region,
                "municipality": municipality,
                "city": street.get("city"),
                "street": street.get("street"),
                "zipcode": street.get("zipcode"),
                "streetNumber": target.street_no,
            },
            "userType": "Postpaid",
            "fixedPackagesType": "TwoP",
            "eligibleFixedPackagesType": None,
        }
        response = self.session().post(ELIGIBILITY, json=payload)
        if response.status_code != httpx.codes.OK:
            raise ProbeError(f"eligibility returned {response.status_code}")
        return replace(read(response.json()), body=response.text)
