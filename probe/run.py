"""Ask the operators that are due, and keep what they say.

All three at once: they don't depend on each other, and a reader waiting shouldn't pay for
three round trips in a row.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

import psycopg
from psycopg.rows import TupleRow
from psycopg.types.json import Jsonb

from probe.adapter import Adapter, NotAskableError, Probed, Target
from probe.ttl import FAILED, VOLATILE, ttl

WIDTH = 3  # three operators, three sessions, one wait

LAST = """
select ok, serviceable, attempted_at
from probe_attempt
where address_id = %(address)s and provider_id = (select id from provider where code = %(code)s)
order by attempted_at desc
limit 1
"""

ATTEMPT = """
insert into probe_attempt (address_id, provider_id, attempted_at, ok, askable, serviceable, detail, raw)
select %(address)s, p.id, %(at)s, %(ok)s, %(askable)s, %(serviceable)s, %(detail)s, %(raw)s
from provider p where p.code = %(code)s
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

# A conclusive answer is everything the operator sells here now. A line they dropped, or an
# address they now refuse, used to stay serviceable until the old answer expired, up to two
# years later, because nothing ever wrote a no. It's recorded now, with a refusal's lifetime.
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
    """What came back from one operator, or why nothing did."""

    provider: str
    result: Probed | None
    error: str | None = None
    # False when we couldn't put the address to them at all: no spelling for the street, or
    # their list has no such street.
    askable: bool = True


def best(result: Probed) -> Decimal | None:
    """The fastest offer, which sets how long the answer is trusted."""
    quoted = [o.max_down_mbps for o in result.offers if o.max_down_mbps is not None]
    return max(quoted) if quoted else None


def due(conn: psycopg.Connection[TupleRow], address_id: int, code: str, now: datetime) -> bool:
    """Whether this operator may be asked again yet.

    A failure gets a few hours' rest. Hitting a broken endpoint on every request is how a rate
    limit becomes a ban, and the answer won't have improved in between.
    """
    row = conn.execute(LAST, {"address": address_id, "code": code}).fetchone()
    if row is None:
        return True
    ok, serviceable, attempted_at = row
    since: datetime = attempted_at
    if not ok:
        return since + FAILED <= now
    if serviceable is False:
        return since + VOLATILE <= now
    return True


def ask(conn: psycopg.Connection[TupleRow], adapter: Adapter, target: Target) -> Reply:
    """One operator, failures caught so one being down can't take the others with it."""
    try:
        return Reply(provider=adapter.code, result=adapter.check(conn, target))
    except NotAskableError as gap:
        # our gap: the adapter had nothing to look the address up by, and said so
        return Reply(provider=adapter.code, result=None, error=str(gap), askable=False)
    except Exception as error:
        return Reply(provider=adapter.code, result=None, error=str(error))


def store(
    conn: psycopg.Connection[TupleRow],
    address_id: int,
    reply: Reply,
    now: datetime,
    keep_raw: bool = False,
) -> int:
    """Always record the attempt, and the answer when there was one.

    The raw body is kept on request, which canaries make so it can be compared over time.
    """
    result = reply.result
    conclusive = result is not None and result.conclusive
    conn.execute(ATTEMPT, {
        "address": address_id,
        "code": reply.provider,
        "at": now,
        "ok": conclusive,
        "askable": reply.askable,
        "serviceable": result.serviceable if result is not None and conclusive else None,
        "detail": reply.error if result is None else None,
        "raw": (
            result.body if result is not None and (keep_raw or not conclusive) else None
        ),
    })
    if result is None or not conclusive:
        return 0

    conn.execute(RETIRE, {
        "address": address_id,
        "code": reply.provider,
        "at": now,
        "until": now + VOLATILE,
        "offered": [offer.technology for offer in result.offers],
    })

    until = now + ttl(best(result), serviceable=result.serviceable)
    kept = 0
    for offer in result.offers:
        conn.execute(KEEP, {
            "address": address_id,
            "code": reply.provider,
            "technology": offer.technology,
            "max_down": offer.max_down_mbps,
            "avg_down": offer.avg_down_mbps,
            "avg_up": offer.avg_up_mbps,
            "at": now,
            "until": until,
            "raw": Jsonb(result.raw) if result.raw is not None else None,
        })
        kept += 1
    return kept


def refresh(
    conn: psycopg.Connection[TupleRow],
    target: Target,
    adapters: list[Adapter],
    now: datetime,
    keep_raw: bool = False,
) -> dict[str, Reply]:
    """Ask every due operator at once and keep what comes back."""
    todo = [a for a in adapters if due(conn, target.address_id, a.code, now)]
    if not todo:
        return {}

    # One shared connection: psycopg serialises its use across threads, and the adapters only
    # read a row of spelling. The waiting is all network.
    with ThreadPoolExecutor(max_workers=min(WIDTH, len(todo))) as pool:
        replies = list(pool.map(lambda a: ask(conn, a, target), todo))

    for answer in replies:
        store(conn, target.address_id, answer, now, keep_raw=keep_raw)
    conn.commit()
    return {a.provider: a for a in replies}


def target_for(conn: psycopg.Connection[TupleRow], address_id: int) -> Target | None:
    """One address in every form an operator might want it."""
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
