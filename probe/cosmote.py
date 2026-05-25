"""Ask Cosmote what it will sell at an address.

They want their own hierarchy, and it is not ours: only 164 of their 506 municipalities
share a name with a Καλλικράτης one, because theirs are the pre-Καλλικράτης list. The
scrape recorded their spelling for every street it walked, so naming() reads it back rather
than walking their dropdowns again, which is six requests to learn one street.

Their checker currently answers that every address needs looking into by hand. That is an
outcome, not a failure, and it is deliberately never cached: writing it down as a refusal
would have the cache repeat it for six months.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser

import httpx
import psycopg
from psycopg.rows import TupleRow

from db.settings import settings
from probe.adapter import Offer, Probed, Target

BASE = "https://www.telekom.gr"
ELIGIBILITY = "/eshop/jsp/eligibility.jsp"
AVAILABILITY = "/eshop/jsp/ajax/avdslavailabilityAjaxV2.jsp"

# What their answer says when it will not decide online.
INCONCLUSIVE = "διερεύνηση"

# Speed names the medium, as it does in their own plan codes: vectored copper stops short
# of 200 Mbps, and a hundred over copper is vectored by definition.
RUNGS = ((200, "FTTH"), (100, "VECT_VDSL"), (50, "VDSL"), (0, "ADSL"))

NAMING = """
select nomos, dimos, area, street
from raw_cosmote
where municipality_id = %s and street_fold = %s
limit 1
"""


class ProbeError(RuntimeError):
    """The checker could not be asked. Not an answer, and never cached as one."""


@dataclass(frozen=True)
class Naming:
    """One address, spelled the way this operator spells it."""

    nomos: str
    dimos: str
    area: str | None
    street: str


def naming(
    conn: psycopg.Connection[TupleRow], municipality_id: int, street_fold: str
) -> Naming | None:
    """Their spelling of this street, if the scrape ever walked it."""
    row = conn.execute(NAMING, (municipality_id, street_fold)).fetchone()
    if row is None:
        return None
    return Naming(nomos=str(row[0]), dimos=str(row[1]),
                  area=None if row[2] is None else str(row[2]), street=str(row[3]))


def technology_of(mbps: int) -> str:
    for floor, technology in RUNGS:
        if mbps >= floor:
            return technology
    return "ADSL"


def mbps(value: str) -> Decimal | None:
    try:
        return Decimal(value.replace(",", ".").strip())
    except (InvalidOperation, ValueError):
        return None


class SpeedTable(HTMLParser):
    """The estimate table, which they key by nominal speed.

    One tbody per rung, id "speed100" and so on. Its second row is download and its third
    upload, each of them a label followed by maximum, usual and minimum.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: dict[int, list[list[str]]] = {}
        self.rung: int | None = None
        self.row: list[str] | None = None
        self.cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        value = dict(attrs)
        if tag == "tbody":
            found = str(value.get("id", ""))
            digits = found[len("speed"):]
            self.rung = int(digits) if found.startswith("speed") and digits.isdigit() else None
        elif tag == "tr" and self.rung is not None:
            self.row = []
        elif tag == "td" and self.row is not None:
            self.cell = []

    def handle_data(self, data: str) -> None:
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "td" and self.cell is not None and self.row is not None:
            self.row.append(" ".join("".join(self.cell).split()))
            self.cell = None
        elif tag == "tr" and self.row is not None and self.rung is not None:
            self.rows.setdefault(self.rung, []).append(self.row)
            self.row = None
        elif tag == "tbody":
            self.rung = None


def offers(html: str) -> tuple[Offer, ...]:
    """Every rung the estimate table quotes, fastest first within each technology."""
    table = SpeedTable()
    table.feed(html)

    best: dict[str, Offer] = {}
    for rung, rows in sorted(table.rows.items()):
        download = next((r for r in rows if len(r) >= 4), None)
        if download is None:
            continue
        technology = technology_of(rung)
        held = best.get(technology)
        if held is not None and held.max_down_mbps is not None and held.max_down_mbps >= rung:
            continue
        best[technology] = Offer(
            technology=technology,
            max_down_mbps=mbps(download[1]),
            avg_down_mbps=mbps(download[2]),
        )
    return tuple(best[code] for code in sorted(best))


def read(html: str) -> Probed:
    """The answer, parsed. Pure, so the shape is tested without asking anyone."""
    if INCONCLUSIVE in html:
        return Probed(serviceable=False, conclusive=False, raw={"reason": "needs investigation"})
    found = offers(html)
    return Probed(serviceable=bool(found), offers=found,
                  raw={"technologies": [o.technology for o in found]})


@dataclass
class Cosmote:
    """A session against their eligibility page, reused across checks."""

    code: str = "OTE"
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
                "Referer": f"{BASE}{ELIGIBILITY}",
                "Origin": BASE,
                "X-Requested-With": "XMLHttpRequest",
            },
        )
        client.get(ELIGIBILITY)
        self.client = client
        return client

    def form(self, target: Target, named: Naming) -> dict[str, str]:
        return {
            "mTelno": "",
            "mState": f"Ν. {named.nomos}",
            "mPrefecture": f"Δ. {named.dimos}",
            "mArea": named.area if named.area is not None else named.dimos,
            "mAddress": named.street,
            "mNumber": target.street_no,
            "searchcriteria": "address",
            "ct": "res",
        }

    def check(self, target: Target, named: Naming) -> Probed:
        response = self.session().post(AVAILABILITY, data=self.form(target, named))
        if response.status_code != httpx.codes.OK:
            raise ProbeError(f"availability returned {response.status_code}")
        return read(response.text)
