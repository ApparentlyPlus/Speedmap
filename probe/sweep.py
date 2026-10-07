"""Re-ask about addresses whose answers are about to expire.

Otherwise the cache only improves where someone happens to look, and the places nobody looks
at are exactly where the register is weakest.
"""

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

# Addresses per run, three operators each. A night is a few hundred requests over hours,
# less than one person browsing for ten minutes.
BUDGET = 200

# Seconds between addresses. A checker that answers a stranger in two seconds can wait two
# more before the next question, and none of this is urgent.
PACE = 2.0

# answers this close to expiry get refreshed now, not at midnight tomorrow
SOON = "1 day"

# Where more people live, more people will ask. premises is the register's count of homes
# behind a point, so it orders the queue by how many people the answer is for.
DUE = """
select a.id
from address a
join availability v on v.address_id = a.id
where v.expires_at <= %(before)s + %(soon)s::interval
group by a.id
order by coalesce(max(a.premises), 1) desc, min(v.expires_at)
limit %(budget)s
"""


def stale(conn: psycopg.Connection[TupleRow], now: datetime, budget: int) -> list[int]:
    """Addresses most worth re-asking, most lived-in first."""
    rows = conn.execute(DUE, {"before": now, "soon": SOON, "budget": budget}).fetchall()
    return [int(row[0]) for row in rows]


def sweep(
    conn: psycopg.Connection[TupleRow],
    adapters: list[Adapter],
    now: datetime,
    budget: int = BUDGET,
    pace: float = PACE,
) -> tuple[int, int]:
    """Ask about each in turn. Returns (addresses asked, operators that answered)."""
    reply = answered = 0
    for address_id in stale(conn, now, budget):
        target = target_for(conn, address_id)
        if target is None:
            continue
        found = refresh(conn, target, adapters, datetime.now(UTC))
        if not found:
            continue
        reply += 1
        answered += sum(1 for a in found.values() if a.result is not None)
        time.sleep(pace)
    return reply, answered


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--budget", type=int, default=BUDGET)
    parser.add_argument("--pace", type=float, default=PACE)
    args = parser.parse_args(argv)

    adapters: list[Adapter] = [Cosmote(), Vodafone(), Nova()]
    with connect() as conn:
        reply, answered = sweep(conn, adapters, datetime.now(UTC), budget=args.budget, pace=args.pace)
    print(f"  sweep: {reply} addresses asked, {answered} operators answered")
    return 0


if __name__ == "__main__":
    sys.exit(main())
