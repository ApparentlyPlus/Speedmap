"""Ask the operators that need asking, and keep what they say.

The three are asked at once because they do not know about each other and a person waiting
should not pay for that three times over.
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

# Three operators, three sessions, one wait.
WIDTH = 3

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


@dataclass(frozen=True)
class Reply:
    """What came back from asking one operator, or why nothing did."""

    provider: str
    result: Probed | None
    error: str | None = None
    # False when the address could not be put to this operator at all, we hold no spelling for
    # the street, or their own list has no such street.
    askable: bool = True


def best(result: Probed) -> Decimal | None:
    """The fastest thing offered, which is what the answer's lifetime is keyed on."""
    quoted = [o.max_down_mbps for o in result.offers if o.max_down_mbps is not None]
    return max(quoted) if quoted else None


def due(conn: psycopg.Connection[TupleRow], address_id: int, code: str, now: datetime) -> bool:
    """Whether this operator may be asked again yet.

    A failure is left alone for a few hours: asking a broken endpoint on every request is
    how a rate limit turns into a ban, and the answer will not have improved in between.
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
    """One operator, with its failure caught: one being down must not take the others."""
    try:
        return Reply(provider=adapter.code, result=adapter.check(conn, target))
    except NotAskableError as gap:
        # Not a failure of theirs. The adapter looked, found it had nothing to look the
        # address up by, and said so, which is the only correct thing it could have done.
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
    """Record the attempt always, and the answer only when there was one.

    The body is kept when it was asked for, a canary, whose point is to be compared over
    time.
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
    """Ask every operator that is due, at once, and keep what comes back."""
    todo = [a for a in adapters if due(conn, target.address_id, a.code, now)]
    if not todo:
        return {}

    # A separate connection per worker would be the alternative, and two of the adapters
    # only read a row of spelling: the asking is network-bound and the reads are not.
    with ThreadPoolExecutor(max_workers=min(WIDTH, len(todo))) as pool:
        replies = list(pool.map(lambda a: ask(conn, a, target), todo))

    for answer in replies:
        store(conn, target.address_id, answer, now, keep_raw=keep_raw)
    conn.commit()
    return {a.provider: a for a in replies}


def target_for(conn: psycopg.Connection[TupleRow], address_id: int) -> Target | None:
    """One address in every form an operator might want to be given it."""
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
