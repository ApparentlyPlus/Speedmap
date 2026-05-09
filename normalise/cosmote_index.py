"""Match the operator's answers to our addresses and cache them as availability.

Folding happens here rather than in SQL because the address index was built with
street_key(), and a second implementation in SQL would drift from it silently.
"""

from __future__ import annotations

import psycopg
from psycopg.rows import TupleRow

from normalise.text import street_key

CHUNK = 50_000

# How long an answer is trusted before it is asked again. Footprints grow rather than
# shrink, so this is about the plan list going out of date, not the line disappearing.
TTL_DAYS = 180

PLANS = "select code, down_mbps, technology from cosmote_plan"

ADDRESSES = """
select municipality_id, street_fold, street_no, id
from address
where municipality_id is not null and street_no is not null
"""

READ = """
select c.id, x.municipality_id, c.street, c.street_no, c.plans, c.observed_at
from raw_cosmote c
join cosmote_area x on x.dimos = c.dimos and x.area = coalesce(c.area, '')
where c.id > %s
order by c.id
limit %s
"""

STAGE = """
create temp table stage_cosmote (
    address_id bigint,
    technology text,
    max_down_mbps numeric,
    observed_at timestamp,
    plans text
) on commit drop
"""

# The scrape only ever recorded a serviceable answer, so serviceable is true throughout.
# An address the operator refuses is absent from the scrape, not present with an empty list.
MERGE = """
insert into availability (
    address_id, provider_id, technology, max_down_mbps, serviceable,
    source, assertion, observed_at, expires_at, raw
)
select distinct on (s.address_id)
    s.address_id, p.id, s.technology, s.max_down_mbps, true,
    'isp-live', 'declared',
    s.observed_at at time zone 'Europe/Athens',
    (s.observed_at at time zone 'Europe/Athens') + make_interval(days => %(ttl)s),
    jsonb_build_object('plans', s.plans)
from stage_cosmote s
cross join (select id from provider where code = 'OTE') p
order by s.address_id, s.observed_at desc, s.max_down_mbps desc
on conflict (address_id, provider_id, technology) do update set
    max_down_mbps = excluded.max_down_mbps,
    serviceable = excluded.serviceable,
    source = excluded.source,
    assertion = excluded.assertion,
    observed_at = excluded.observed_at,
    expires_at = excluded.expires_at,
    raw = excluded.raw
"""


def best_plan(
    plans: str, catalogue: dict[str, tuple[float, str]]
) -> tuple[float, str] | None:
    """The fastest plan the operator offers here, which is what names the technology.

    Vectored copper stops short of 200 Mbps, so the top rung says what is in the ground.
    An unknown code is ignored rather than guessed: a new one is a catalogue change.
    """
    known = [catalogue[code] for code in plans.split(",") if code in catalogue]
    return max(known) if known else None


def rows(
    conn: psycopg.Connection[TupleRow],
    index: dict[tuple[int, str, str], int],
    catalogue: dict[str, tuple[float, str]],
    after: int,
) -> tuple[list[tuple[object, ...]], int | None]:
    """One chunk, matched. Returns the staged rows and the key to resume from."""
    read = conn.execute(READ, (after, CHUNK)).fetchall()
    if not read:
        return [], None

    staged: list[tuple[object, ...]] = []
    for _, municipality_id, street, street_no, plans, observed_at in read:
        address_id = index.get((municipality_id, street_key(street), str(street_no)))
        if address_id is None:
            continue
        best = best_plan(plans, catalogue)
        if best is None:
            continue
        mbps, technology = best
        staged.append((address_id, technology, mbps, observed_at, plans))
    return staged, int(read[-1][0])


def build_cosmote_index(conn: psycopg.Connection[TupleRow]) -> int:
    catalogue = {
        code: (float(mbps), technology)
        for code, mbps, technology in conn.execute(PLANS).fetchall()
    }
    index = {
        (municipality_id, street_fold, street_no): address_id
        for municipality_id, street_fold, street_no, address_id in conn.execute(ADDRESSES)
    }

    conn.execute(STAGE)
    written = 0
    after = 0
    while True:
        # The chunk is read in full before the copy opens: a select and a copy cannot
        # share one connection, and interleaving them deadlocks on ClientRead.
        staged, resume = rows(conn, index, catalogue, after)
        if resume is None:
            break
        if staged:
            with conn.cursor().copy(
                "copy stage_cosmote (address_id, technology, max_down_mbps, observed_at, plans) "
                "from stdin"
            ) as copy:
                for row in staged:
                    copy.write_row(row)
            written += len(staged)
        after = resume

    conn.execute(MERGE, {"ttl": TTL_DAYS})
    return written

