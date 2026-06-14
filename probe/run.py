"""Ask the operators that need asking, and keep what they say.

The three are asked at once because they do not know about each other and a person waiting
should not pay for that three times over. Each answer is written under a lifetime that
depends on the answer, so a gigabit is settled for two years and a slow line is asked again
next month.

Failure is handled separately throughout. An operator that could not be reached is recorded
as not reached, never as offering nothing, and is left alone for a few hours rather than
retried on every request until someone notices.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

import psycopg
from psycopg.rows import TupleRow
from psycopg.types.json import Jsonb

from probe.adapter import Adapter, Probed, Target
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
insert into probe_attempt (address_id, provider_id, attempted_at, ok, serviceable, detail, raw)
select %(address)s, p.id, %(at)s, %(ok)s, %(serviceable)s, %(detail)s, %(raw)s
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
class Asked:
    """What came back from asking one operator, or why nothing did."""

    provider: str
    probed: Probed | None
    error: str | None = None


def best(probed: Probed) -> Decimal | None:
    """The fastest thing offered, which is what the answer's lifetime is keyed on."""
    quoted = [o.max_down_mbps for o in probed.offers if o.max_down_mbps is not None]
    return max(quoted) if quoted else None


def due(conn: psycopg.Connection[TupleRow], address_id: int, code: str, now: datetime) -> bool:
    """Whether this operator may be asked again yet.

    A failure is left alone for a few hours: asking a broken endpoint on every request is
    how a rate limit turns into a ban, and the answer will not have improved in between.

    A refusal is left alone for a month. It leaves no row in availability to expire, so
    without this it would be asked again on every visit to the address for ever, which is
    the same mistake spread thinner.
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


def ask(conn: psycopg.Connection[TupleRow], adapter: Adapter, target: Target) -> Asked:
    """One operator, with its failure caught: one being down must not take the others."""
    try:
        return Asked(provider=adapter.code, probed=adapter.check(conn, target))
    except Exception as error:
        return Asked(provider=adapter.code, probed=None, error=str(error))


def store(
    conn: psycopg.Connection[TupleRow],
    address_id: int,
    asked: Asked,
    now: datetime,
    keep_raw: bool = False,
) -> int:
    """Record the attempt always, and the answer only when there was one.

    The body is kept when it was asked for — a canary, whose point is to be compared over
    time — and whenever the answer was not conclusive, which is when a parser is most
    likely to be the thing at fault. A nightly sweep keeps none of it: two hundred
    addresses of identical HTML answers no question anyone will ask.
    """
    probed = asked.probed
    conclusive = probed is not None and probed.conclusive
    conn.execute(ATTEMPT, {
        "address": address_id,
        "code": asked.provider,
        "at": now,
        "ok": conclusive,
        "serviceable": probed.serviceable if probed is not None and conclusive else None,
        "detail": asked.error if probed is None else None,
        "raw": (
            probed.body if probed is not None and (keep_raw or not conclusive) else None
        ),
    })
    if probed is None or not conclusive:
        return 0

    until = now + ttl(best(probed), serviceable=probed.serviceable)
    written = 0
    for offer in probed.offers:
        conn.execute(KEEP, {
            "address": address_id,
            "code": asked.provider,
            "technology": offer.technology,
            "max_down": offer.max_down_mbps,
            "avg_down": offer.avg_down_mbps,
            "avg_up": offer.avg_up_mbps,
            "at": now,
            "until": until,
            "raw": Jsonb(probed.raw) if probed.raw is not None else None,
        })
        written += 1
    return written


def refresh(
    conn: psycopg.Connection[TupleRow],
    target: Target,
    adapters: list[Adapter],
    now: datetime,
    keep_raw: bool = False,
) -> dict[str, Asked]:
    """Ask every operator that is due, at once, and keep what comes back."""
    wanted = [a for a in adapters if due(conn, target.address_id, a.code, now)]
    if not wanted:
        return {}

    # A separate connection per worker would be the alternative, and two of the adapters
    # only read a row of spelling: the asking is network-bound and the reads are not.
    with ThreadPoolExecutor(max_workers=min(WIDTH, len(wanted))) as pool:
        answers = list(pool.map(lambda a: ask(conn, a, target), wanted))

    for answer in answers:
        store(conn, target.address_id, answer, now, keep_raw=keep_raw)
    conn.commit()
    return {a.provider: a for a in answers}


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
