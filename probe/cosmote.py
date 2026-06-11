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

from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser

import httpx
import psycopg
from psycopg.rows import TupleRow

from db.settings import settings
from probe.adapter import Offer, Probed, Target
from probe.naming import Naming, naming

BASE = "https://www.telekom.gr"
ELIGIBILITY = "/eshop/jsp/eligibility.jsp"
AVAILABILITY = "/eshop/jsp/ajax/avdslavailabilityAjaxV2.jsp"

# What their answer says when it will not decide online.
INCONCLUSIVE = "διερεύνηση"

# Speed names the medium, as it does in their own plan codes: vectored copper stops short
# of 200 Mbps, and a hundred over copper is vectored by definition. The floor for VDSL is 25
# rather than 50 because ADSL cannot pass 24, which the technology table records as its
# ceiling: their 30 Mbps rung is a VDSL line sold short, not a fast ADSL one.
RUNGS = ((200, "FTTH"), (100, "VECT_VDSL"), (25, "VDSL"), (0, "ADSL"))


class ProbeError(RuntimeError):
    """The checker could not be asked. Not an answer, and never cached as one."""


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


def line(rows: list[list[str]], label: str) -> list[str] | None:
    """The row for one direction. The first four-cell row is the header, not a measurement:
    its cells read Μέγιστη, Συνήθης, Ελάχιστη, which parse as no speed at all."""
    for row in rows:
        if len(row) >= 4 and row[0].upper().startswith(label):
            return row
    return None


def offers(html: str) -> tuple[Offer, ...]:
    """Every rung the estimate table quotes, fastest first within each technology."""
    table = SpeedTable()
    table.feed(html)

    best: dict[str, Offer] = {}
    for rung, rows in sorted(table.rows.items()):
        download = line(rows, "DOWNLOAD")
        if download is None:
            continue
        upload = line(rows, "UPLOAD")
        technology = technology_of(rung)
        held = best.get(technology)
        if held is not None and held.max_down_mbps is not None and held.max_down_mbps >= rung:
            continue
        best[technology] = Offer(
            technology=technology,
            max_down_mbps=mbps(download[1]),
            avg_down_mbps=mbps(download[2]),
            avg_up_mbps=None if upload is None else mbps(upload[2]),
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

    def addressed(self, named: Naming) -> str:
        """Their spelling of a street, which carries its type in brackets.

        Without it the answer is that the address needs looking into by hand, whatever else
        the request gets right. Case and accent do not matter to them; the brackets do.
        """
        if named.street_type is None:
            return named.street
        return f"{named.street} ({named.street_type})"

    def form(self, target: Target, named: Naming) -> dict[str, str]:
        return {
            "mTelno": "",
            "mState": f"Ν. {named.nomos}",
            "mPrefecture": f"Δ. {named.dimos}",
            "mArea": named.area if named.area is not None else named.dimos,
            "mAddress": self.addressed(named),
            "mNumber": target.street_no,
            "searchcriteria": "address",
            "ct": "res",
        }

    def check(self, conn: psycopg.Connection[TupleRow], target: Target) -> Probed:
        named = naming(conn, target.municipality_id, target.street_fold)
        if named is None:
            raise ProbeError(f"no spelling recorded for {target.street}")
        response = self.session().post(AVAILABILITY, data=self.form(target, named))
        if response.status_code != httpx.codes.OK:
            raise ProbeError(f"availability returned {response.status_code}")
        return replace(read(response.text), body=response.text)
