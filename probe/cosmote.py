"""Ask Telekom (Cosmote's checker) what it sells at an address.

They want their own hierarchy: only 164 of their 506 municipalities share a name with a
Καλλικράτης one, because theirs is the pre-Καλλικράτης list.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser

import httpx
import psycopg
from psycopg.rows import TupleRow

from db.settings import settings
from probe.adapter import NotAskableError, Offer, Probed, ProbeError, Target
from probe.descriptor import Descriptor
from probe.naming import Naming, naming
from probe.walls import refuse

SPEC = Descriptor("TELEKOM")

BASE = SPEC.text("base")
ELIGIBILITY = SPEC.text("warm")
AVAILABILITY = SPEC.text("availability")

# what their answer says when it won't decide online
INCONCLUSIVE = SPEC.text("inconclusive")

# Speed names the medium, as in their plan codes: vectored copper stops short of 200 Mbps,
# and 100 over copper is vectored by definition.
RUNGS = SPEC.rungs()


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
    """Their estimate table, keyed by nominal speed.

    One tbody per rung (id "speed100" and so on). Row two is download, row three upload, each
    a label then maximum, usual and minimum.
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
    """The row for one direction. The first four-cell row is the header (Μέγιστη, Συνήθης,
    Ελάχιστη), which parses as no speed at all."""
    for row in rows:
        if len(row) >= 4 and row[0].upper().startswith(label):
            return row
    return None


def offers(html: str) -> tuple[Offer, ...]:
    """Every rung the table quotes, keeping the fastest per technology."""
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
    """Parse the answer. Pure, so the shape can be tested offline."""
    if INCONCLUSIVE in html:
        return Probed(serviceable=False, conclusive=False, raw={"reason": "needs investigation"})
    found = offers(html)
    return Probed(serviceable=bool(found), offers=found,
                  raw={"technologies": [o.technology for o in found]})


@dataclass
class Cosmote:
    """A session on their eligibility page, reused across checks."""

    code: str = "TELEKOM"
    client: httpx.Client | None = None
    user_agent: str = settings.user_agent

    def session(self) -> httpx.Client:
        if self.client is not None:
            return self.client
        client = httpx.Client(
            base_url=BASE,
            timeout=30.0,
            # a block page fails the request here, before it's read as an answer
            event_hooks={"response": [refuse]},
            headers={
                "User-Agent": self.user_agent,
                "Referer": f"{BASE}{ELIGIBILITY}",
                "Origin": BASE,
                **SPEC.mapping("headers"),
            },
        )
        client.get(ELIGIBILITY)
        self.client = client
        return client

    def addressed(self, named: Naming) -> str:
        """Their spelling of a street, with its type in brackets.

        Without the brackets they answer that the address needs checking by hand, whatever else
        is right. Case and accents don't matter to them.
        """
        if named.street_type is None:
            return named.street
        return f"{named.street} ({named.street_type})"

    def form(self, target: Target, named: Naming) -> dict[str, str]:
        field = SPEC.mapping("form")
        return {
            field["telephone"]: "",
            field["prefecture"]: SPEC.text("prefecture_prefix") + named.nomos,
            field["municipality"]: SPEC.text("municipality_prefix") + named.dimos,
            field["area"]: named.area if named.area is not None else named.dimos,
            field["street"]: self.addressed(named),
            field["number"]: target.street_no,
            **SPEC.mapping("constants"),
        }

    def check(self, conn: psycopg.Connection[TupleRow], target: Target) -> Probed:
        """Only streets the scrape walked. We tried guessing the rest against their live
        checker, and it didn't work.
        """
        named = naming(conn, target.municipality_id, target.street_fold)
        if named is None:
            raise NotAskableError(f"no spelling recorded for {target.street}")
        response = self.session().post(AVAILABILITY, data=self.form(target, named))
        if response.status_code != httpx.codes.OK:
            raise ProbeError(f"availability returned {response.status_code}")
        return replace(read(response.text), body=response.text)
