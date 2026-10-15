"""Re-ask about addresses whose answers are about to expire, before anyone looks."""

from __future__ import annotations

import argparse
import sys
import time
from datetime import UTC, datetime

import psycopg
from psycopg.rows import TupleRow

from db.connect import connect
from probe.adapter import Adapter
from probe.cosmote import Cosmote
from probe.nova import Nova
from probe.run import refresh, target_for
from probe.vodafone import Vodafone

BUDGET = 200  # addresses a night, less traffic than one person browsing
PACE = 2.0  # seconds between addresses

SOON = "1 day"

# asked lately and still due means it didn't work, don't let it eat every night's budget
REST = "7 days"

# most premises first
DUE = """
select a.id
from address a
join availability v on v.address_id = a.id
where v.expires_at <= %(before)s + %(soon)s::interval
  and not exists (
      select 1 from probe_attempt pa
      where pa.address_id = a.id and pa.attempted_at > %(before)s - %(rest)s::interval
  )
group by a.id
order by coalesce(max(a.premises), 1) desc, min(v.expires_at)
limit %(budget)s
"""


def stale(conn: psycopg.Connection[TupleRow], now: datetime, budget: int) -> list[int]:
    rows = conn.execute(DUE, {"before": now, "soon": SOON, "rest": REST, "budget": budget}).fetchall()
    return [int(r[0]) for r in rows]


def sweep(conn: psycopg.Connection[TupleRow], adapters: list[Adapter], now: datetime, budget: int = BUDGET,
          pace: float = PACE) -> tuple[int, int]:
    """(addresses asked, operators that answered)"""
    asked = answered = 0
    for aid in stale(conn, now, budget):
        target = target_for(conn, aid)
        if target is None:
            continue
        found = refresh(conn, target, adapters, datetime.now(UTC))
        if not found:
            continue
        asked += 1
        answered += sum(1 for a in found.values() if a.result is not None)
        time.sleep(pace)
    return asked, answered


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--budget", type=int, default=BUDGET)
    parser.add_argument("--pace", type=float, default=PACE)
    args = parser.parse_args(argv)

    adapters: list[Adapter] = [Cosmote(), Vodafone(), Nova()]
    with connect() as conn:
        asked, answered = sweep(conn, adapters, datetime.now(UTC), budget=args.budget, pace=args.pace)
    print(f"  sweep: {asked} addresses asked, {answered} operators answered")
    return 0


if __name__ == "__main__":
    sys.exit(main())
