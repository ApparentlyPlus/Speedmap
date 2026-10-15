"""Ask the operators that are due, all at once, and keep what they say."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

import psycopg
from psycopg.rows import TupleRow
from psycopg.types.json import Jsonb

from alert import alert_later
from probe.adapter import Adapter, NotAskableError, Probed, Target
from probe.ttl import FAILED, VOLATILE, ttl
from probe.walls import BlockedError

WIDTH = 3

LAST = """
select ok, serviceable, attempted_at
from probe_attempt
where address_id = %(address)s and provider_id = (select id from provider where code = %(code)s)
order by attempted_at desc
limit 1
"""

ATTEMPT = """
insert into probe_attempt (
    address_id, provider_id, attempted_at, ok, askable, serviceable, detail, raw, blocked
)
select %(address)s, p.id, %(at)s, %(ok)s, %(askable)s, %(serviceable)s, %(detail)s, %(raw)s,
       %(blocked)s
from provider p where p.code = %(code)s
"""

# a block rests the whole operator, doubling per block in a row
REST = timedelta(minutes=30)
LONGEST_REST = timedelta(hours=12)

STREAK = """
select a.blocked, a.attempted_at
from probe_attempt a
where a.provider_id = (select id from provider where code = %(code)s)
order by a.attempted_at desc
limit 8
"""

PER_MINUTE = 12  # API and sweep together, per operator

RECENT = """
select count(*)
from probe_attempt a
where a.provider_id = (select id from provider where code = %(code)s)
  and a.attempted_at > %(since)s
"""

KEEP = """
insert into availability (
    address_id, provider_id, technology, max_down_mbps, avg_down_mbps, avg_up_mbps,
    serviceable, source, assertion, observed_at, expires_at, raw
)
select %(address)s, p.id, %(technology)s, %(max_down)s, %(avg_down)s, %(avg_up)s,
       true, 'isp-live', 'declared', %(at)s, %(until)s, %(raw)s
from provider p where p.code = %(code)s
on conflict (address_id, provider_id, technology) do update set
    max_down_mbps = excluded.max_down_mbps,
    avg_down_mbps = excluded.avg_down_mbps,
    avg_up_mbps = excluded.avg_up_mbps,
    serviceable = excluded.serviceable,
    source = excluded.source,
    assertion = excluded.assertion,
    observed_at = excluded.observed_at,
    expires_at = excluded.expires_at,
    raw = excluded.raw
"""

# a conclusive answer is the full list, so anything missing from it is now a no
RETIRE = """
update availability v
set serviceable = false, observed_at = %(at)s, expires_at = %(until)s
from provider p
where p.code = %(code)s and v.provider_id = p.id
  and v.address_id = %(address)s
  and v.source = 'isp-live'
  and v.serviceable
  and v.technology <> all(%(offered)s)
"""


@dataclass(frozen=True)
class Reply:
    provider: str
    result: Probed | None
    error: str | None = None
    askable: bool = True  # False if we had no spelling of the street for them
    blocked: str | None = None  # whose wall answered


def best(result: Probed) -> Decimal | None:
    quoted = [o.max_down_mbps for o in result.offers if o.max_down_mbps is not None]
    return max(quoted) if quoted else None


def due(conn: psycopg.Connection[TupleRow], address_id: int, code: str, now: datetime) -> bool:
    # hammering a broken endpoint is how a rate limit becomes a ban
    row = conn.execute(LAST, {"address": address_id, "code": code}).fetchone()
    if row is None:
        return True
    ok, serviceable, at = row
    since: datetime = at
    if not ok:
        return since + FAILED <= now
    if serviceable is False:
        return since + VOLATILE <= now
    return True


def resting(conn: psycopg.Connection[TupleRow], code: str, now: datetime) -> datetime | None:
    """When this operator may be asked again, or None if it may now."""
    streak = conn.execute(STREAK, {"code": code}).fetchall()
    n = 0
    for blocked, _ in streak:
        if blocked is None:
            break
        n += 1
    if n == 0:
        return None
    last: datetime = streak[0][1]
    until = last + min(REST * 2 ** (n - 1), LONGEST_REST)
    return until if until > now else None


def crowded(conn: psycopg.Connection[TupleRow], code: str, now: datetime) -> bool:
    row = conn.execute(RECENT, {"code": code, "since": now - timedelta(minutes=1)}).fetchone()
    return row is not None and int(row[0]) >= PER_MINUTE


def ask(conn: psycopg.Connection[TupleRow], adapter: Adapter, target: Target) -> Reply:
    # catch everything, one operator down mustn't take the others with it
    try:
        return Reply(provider=adapter.code, result=adapter.check(conn, target))
    except BlockedError as e:
        return Reply(provider=adapter.code, result=None, error=str(e), blocked=e.wall)
    except NotAskableError as e:
        return Reply(provider=adapter.code, result=None, error=str(e), askable=False)
    except Exception as e:
        return Reply(provider=adapter.code, result=None, error=str(e))


def store(conn: psycopg.Connection[TupleRow], address_id: int, reply: Reply, now: datetime,
          keep_raw: bool = False) -> int:
    """Record the attempt, and the answer if there was one. keep_raw is for the canary."""
    result = reply.result
    conclusive = result is not None and result.conclusive
    prev = conn.execute(STREAK, {"code": reply.provider}).fetchone()
    was_blocked = prev is not None and prev[0] is not None
    if reply.blocked is not None and not was_blocked:
        alert_later(
            f"{reply.provider} is blocking us",
            f"{reply.blocked} answered instead of {reply.provider}. It rests for "
            f"{int(REST.total_seconds() // 60)} minutes, longer if it keeps blocking, and readers "
            "see what the cache holds until then.",
            urgent=True,
        )
    elif conclusive and was_blocked:
        alert_later(f"{reply.provider} is answering again", "Live checks are back on.")
    conn.execute(ATTEMPT, {
        "address": address_id,
        "code": reply.provider,
        "at": now,
        "ok": conclusive,
        "askable": reply.askable,
        "serviceable": result.serviceable if result is not None and conclusive else None,
        "detail": reply.error if result is None else None,
        "raw": result.body if result is not None and (keep_raw or not conclusive) else None,
        "blocked": reply.blocked,
    })
    if result is None or not conclusive:
        return 0

    conn.execute(RETIRE, {
        "address": address_id,
        "code": reply.provider,
        "at": now,
        "until": now + VOLATILE,
        "offered": [o.technology for o in result.offers],
    })

    until = now + ttl(best(result), serviceable=result.serviceable)
    kept = 0
    for o in result.offers:
        conn.execute(KEEP, {
            "address": address_id,
            "code": reply.provider,
            "technology": o.technology,
            "max_down": o.max_down_mbps,
            "avg_down": o.avg_down_mbps,
            "avg_up": o.avg_up_mbps,
            "at": now,
            "until": until,
            "raw": Jsonb(result.raw) if result.raw is not None else None,
        })
        kept += 1
    return kept


def refresh(conn: psycopg.Connection[TupleRow], target: Target, adapters: list[Adapter], now: datetime,
            keep_raw: bool = False) -> dict[str, Reply]:
    todo = [
        a for a in adapters
        if due(conn, target.address_id, a.code, now)
        and resting(conn, a.code, now) is None
        and not crowded(conn, a.code, now)
    ]
    if not todo:
        return {}

    # psycopg serialises the shared connection, the adapters barely touch it
    with ThreadPoolExecutor(max_workers=min(WIDTH, len(todo))) as pool:
        replies = list(pool.map(lambda a: ask(conn, a, target), todo))

    for r in replies:
        store(conn, target.address_id, r, now, keep_raw=keep_raw)
    conn.commit()
    return {r.provider: r for r in replies}


def target_for(conn: psycopg.Connection[TupleRow], address_id: int) -> Target | None:
    row = conn.execute(
        "select a.id, st_y(a.geom::geometry), st_x(a.geom::geometry), a.street, a.street_no, "
        "coalesce(m.name, ''), coalesce(a.municipality_id, 0), a.street_fold, a.locality, "
        "a.postcode from address a left join municipality m on m.id = a.municipality_id "
        "where a.id = %s",
        (address_id,),
    ).fetchone()
    if row is None:
        return None
    return Target(
        address_id=int(row[0]), lat=float(row[1]), lon=float(row[2]),
        street=str(row[3]), street_no=str(row[4]) if row[4] is not None else "",
        municipality=str(row[5]), municipality_id=int(row[6]),
        street_fold=str(row[7]),
        locality=None if row[8] is None else str(row[8]),
        postcode=None if row[9] is None else str(row[9]),
    )
