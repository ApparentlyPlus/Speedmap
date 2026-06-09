"""Re-ask about the addresses whose answers are about to stop being true.

Without this the cache only improves where someone happens to look, and the addresses
nobody looks at are exactly the ones the register is worst about. A nightly pass over the
oldest answers means traffic is not the only thing that sharpens the map.

The queue is the query. An answer that is refreshed gets a new expiry and falls out of it;
one that fails is held off by its own backoff. Nothing else has to remember where the last
run stopped, which is what makes an interrupted run cost nothing.
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

# How many addresses one run will ask about. Three operators each, so a night of this is a
# few hundred requests spread over hours: less than one person browsing for ten minutes.
BUDGET = 200

# Seconds between addresses. The point is not to be fast. A checker that answers a stranger
# in two seconds should not be asked again for two more, and nothing here is urgent.
PACE = 2.0

# Answers this close to expiring are worth refreshing now rather than at midnight tomorrow.
SOON = "1 day"

# Where more people live, more people will ask. Premises is the register's own count of
# homes behind a point, so it orders the queue by who the answer is for.
DUE = """
select a.id
from address a
join availability v on v.address_id = a.id
where v.expires_at <= %(before)s + %(soon)s::interval
group by a.id
order by coalesce(max(a.premises), 1) desc, min(v.expires_at)
limit %(budget)s
"""


def stale(
    conn: psycopg.Connection[TupleRow], now: datetime, budget: int
) -> list[int]:
    """The addresses most worth asking about again, most-lived-in first."""
    rows = conn.execute(
        DUE, {"before": now, "soon": SOON, "budget": budget}
    ).fetchall()
    return [int(row[0]) for row in rows]


def sweep(
    conn: psycopg.Connection[TupleRow],
    adapters: list[Adapter],
    now: datetime,
    budget: int = BUDGET,
    pace: float = PACE,
) -> tuple[int, int]:
    """Ask about each in turn. Returns how many were asked and how many answered."""
    asked = answered = 0
    for address_id in stale(conn, now, budget):
        target = target_for(conn, address_id)
        if target is None:
            continue
        found = refresh(conn, target, adapters, datetime.now(UTC))
        if not found:
            continue
        asked += 1
        answered += sum(1 for a in found.values() if a.probed is not None)
        time.sleep(pace)
    return asked, answered


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--budget", type=int, default=BUDGET)
    parser.add_argument("--pace", type=float, default=PACE)
    args = parser.parse_args(argv)

    adapters: list[Adapter] = [Cosmote(), Vodafone(), Nova()]
    with connect() as conn:
        asked, answered = sweep(
            conn, adapters, datetime.now(UTC), budget=args.budget, pace=args.pace
        )
    print(f"  sweep: {asked} addresses asked, {answered} operators answered")
    return 0


if __name__ == "__main__":
    sys.exit(main())
