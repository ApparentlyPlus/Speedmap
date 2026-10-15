"""Telekom's (Cosmote's) checker. Wants pre-Καλλικράτης names, only 164 of 506 match ours."""

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

INCONCLUSIVE = SPEC.text("inconclusive")
RUNGS = SPEC.rungs()  # speed implies the medium, like their plan codes


def technology_of(mbps: int) -> str:
    for floor, technology in RUNGS:
        if mbps >= floor:
            return technology
    return "ADSL"


def mbps(value: str) -> Decimal | None:
    try:
        return Decimal(value.replace(",", ".").strip())  # 12,5
    except (InvalidOperation, ValueError):
        return None


class SpeedTable(HTMLParser):
    """Their estimate table. A tbody per rung (id="speed100"), rows of label, max, usual, min."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: dict[int, list[list[str]]] = {}
        self.rung: int | None = None
        self.row: list[str] | None = None
        self.cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        if tag == "tbody":
            id_ = str(a.get("id", ""))
            n = id_[len("speed"):]
            self.rung = int(n) if id_.startswith("speed") and n.isdigit() else None
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
    # the header row has four cells too but no speeds in it
    for row in rows:
        if len(row) >= 4 and row[0].upper().startswith(label):
            return row
    return None


def offers(html: str) -> tuple[Offer, ...]:
    """Fastest rung per technology."""
    t = SpeedTable()
    t.feed(html)

    best: dict[str, Offer] = {}
    for rung, rows in sorted(t.rows.items()):
        down = line(rows, "DOWNLOAD")
        if down is None:
            continue
        up = line(rows, "UPLOAD")
        tech = technology_of(rung)
        held = best.get(tech)
        if held is not None and held.max_down_mbps is not None and held.max_down_mbps >= rung:
            continue
        best[tech] = Offer(
            technology=tech,
            max_down_mbps=mbps(down[1]),
            avg_down_mbps=mbps(down[2]),
            avg_up_mbps=None if up is None else mbps(up[2]),
        )
    return tuple(best[k] for k in sorted(best))


def read(html: str) -> Probed:
    if INCONCLUSIVE in html:
        return Probed(serviceable=False, conclusive=False, raw={"reason": "needs investigation"})
    found = offers(html)
    return Probed(serviceable=bool(found), offers=found,
                  raw={"technologies": [o.technology for o in found]})


@dataclass
class Cosmote:
    code: str = "TELEKOM"
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
                "Referer": f"{BASE}{ELIGIBILITY}",
                "Origin": BASE,
                **SPEC.mapping("headers"),
            },
        )
        client.get(ELIGIBILITY)
        self.client = client
        return client

    def addressed(self, named: Naming) -> str:
        # ΑΧΑΡΝΩΝ (ΟΔΟΣ). Without the brackets every answer is "needs checking by hand"
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
        # only streets the scrape walked, guessing spellings didn't work
        named = naming(conn, target.municipality_id, target.street_fold)
        if named is None:
            raise NotAskableError(f"no spelling recorded for {target.street}")
        r = self.session().post(AVAILABILITY, data=self.form(target, named))
        if r.status_code != httpx.codes.OK:
            raise ProbeError(f"availability returned {r.status_code}")
        return replace(read(r.text), body=r.text)
