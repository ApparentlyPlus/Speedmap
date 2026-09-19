"""Ask about addresses whose answer is already known.

An adapter that has been redesigned out from under us does not return an error.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import psycopg
import yaml
from psycopg.rows import TupleRow

from db.connect import connect
from probe.adapter import Adapter
from probe.cosmote import Cosmote
from probe.nova import Nova
from probe.run import Reply, ask, store, target_for
from probe.vodafone import Vodafone

CANARIES = Path(__file__).parent / "canaries.yaml"

# What a canary is allowed to expect. Anything subtler is a canary that cries wolf, which
# is worse than none: it gets ignored, and then the real failure is ignored with it.
OFFERS = "offers"
REFUSAL = "refusal"

FIND = """
select a.id
from address a
join municipality m on m.id = a.municipality_id
where m.name = %(municipality)s and a.street_fold = %(street)s and a.street_no = %(number)s
limit 1
"""


@dataclass(frozen=True)
class Canary:
    name: str
    why: str
    municipality: str
    street: str
    street_no: str
    expect: str
    providers: tuple[str, ...] = ()


@dataclass(frozen=True)
class Verdict:
    canary: str
    provider: str
    passed: bool
    detail: str


def load(path: Path = CANARIES) -> list[Canary]:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [
        Canary(
            name=str(entry["name"]),
            why=str(entry["why"]),
            municipality=str(entry["municipality"]),
            street=str(entry["street"]),
            street_no=str(entry["street_no"]),
            expect=str(entry["expect"]),
            providers=tuple(entry.get("providers", ())),
        )
        for entry in document
    ]


def judge(canary: Canary, reply: Reply) -> Verdict:
    """Whether the adapter is working, which is not whether the address has service."""
    result = reply.result
    if result is None:
        return Verdict(canary.name, reply.provider, False, f"unreachable: {reply.error}")
    if not result.conclusive:
        return Verdict(canary.name, reply.provider, False, "answered nothing conclusive")
    if canary.expect == OFFERS and not result.offers:
        # The failure this exists for: a 200, a page, and no offers on a street that has
        # had service for years.
        return Verdict(canary.name, reply.provider, False, "no offers where there are some")
    if canary.expect == REFUSAL and result.serviceable:
        return Verdict(canary.name, reply.provider, False, "offers where there are none")
    return Verdict(canary.name, reply.provider, True, f"{len(result.offers)} offers")


def run(
    conn: psycopg.Connection[TupleRow],
    canaries: list[Canary],
    adapters: list[Adapter],
    now: datetime,
) -> list[Verdict]:
    """Ask every canary of every adapter it names, and keep the bodies for comparison."""
    verdicts: list[Verdict] = []
    for canary in canaries:
        row = conn.execute(FIND, {
            "municipality": canary.municipality,
            "street": canary.street,
            "number": canary.street_no,
        }).fetchone()
        if row is None:
            verdicts.append(Verdict(canary.name, "-", False, "canary address is not in the index"))
            continue
        target = target_for(conn, int(row[0]))
        if target is None:
            continue
        wanted = [a for a in adapters if not canary.providers or a.code in canary.providers]
        for adapter in wanted:
            # Asked directly rather than through refresh: a canary ignores the backoff,
            # because the whole point is to notice while the adapter is still broken.
            answer = ask(conn, adapter, target)
            store(conn, target.address_id, answer, now, keep_raw=True)
            verdicts.append(judge(canary, answer))
        conn.commit()
    return verdicts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", type=Path, default=CANARIES)
    args = parser.parse_args(argv)

    adapters: list[Adapter] = [Cosmote(), Vodafone(), Nova()]
    with connect() as conn:
        verdicts = run(conn, load(args.file), adapters, datetime.now(UTC))

    for verdict in verdicts:
        mark = "ok  " if verdict.passed else "FAIL"
        print(f"  [{mark}] {verdict.canary:18} {verdict.provider:9} {verdict.detail}")
    failed = [v for v in verdicts if not v.passed]
    if failed:
        print(f"  {len(failed)} of {len(verdicts)} canaries failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
