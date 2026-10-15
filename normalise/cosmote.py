"""Fold the Telekom scrape into the address index and the answer cache."""

from __future__ import annotations

import psycopg
from psycopg.rows import TupleRow

from normalise.greeklish import from_greek
from normalise.text import fold, street_key
from probe.ttl import (
    CHANGING,
    FAST,
    GIGABIT,
    LIKELY,
    SETTLED,
    USABLE,
    VOLATILE,
)

CHUNK = 50_000

# which duplicate to keep, rooftop beats interpolated
PRECISION = {"rooftop": 0, "interpolated": 1, "street": 2, "locality": 3}
UNRANKED = len(PRECISION)

# their dimoi aren't Καλλικράτης ones, so place each area by where its points fall
AREA = """
create temp table cosmote_area on commit drop as
select distinct on (c.dimos, coalesce(c.area, ''))
    c.dimos, coalesce(c.area, '') as area, m.id as municipality_id
from raw_cosmote c
join municipality m on st_contains(m.geom_2d, c.geom::geometry)
where c.geocode_precision in ('rooftop', 'interpolated')
group by c.dimos, coalesce(c.area, ''), m.id
order by c.dimos, coalesce(c.area, ''), count(*) desc, m.id
"""

# unlimited airtime has no speed, skip it
CATALOGUE = """
select pl.external_key, pl.down_mbps, pl.technology
from plan pl join provider pr on pr.id = pl.provider_id
where pr.code = 'TELEKOM' and pl.technology is not null and pl.down_mbps is not null
"""

HELD = """
select municipality_id, street_fold, street_no
from address
where municipality_id is not null and street_no is not null
"""

PLACES = """
select c.id, x.municipality_id, c.street, c.street_no, c.area, c.geocode_precision, c.kaek,
       st_x(c.geom::geometry), st_y(c.geom::geometry)
from raw_cosmote c
join cosmote_area x on x.dimos = c.dimos and x.area = coalesce(c.area, '')
where c.geom is not null and c.id > %s
order by c.id
limit %s
"""

ANSWERS = """
select c.id, x.municipality_id, c.street, c.street_no, c.plans, c.observed_at
from raw_cosmote c
join cosmote_area x on x.dimos = c.dimos and x.area = coalesce(c.area, '')
where c.id > %s
order by c.id
limit %s
"""

STAGE_ADDRESS = """
create temp table stage_cosmote_address (
    municipality_id int, street text, street_fold text, street_no text, locality text,
    search_key text, latin_key text, kaek text, lon double precision, lat double precision
) on commit drop
"""

ADD_ADDRESS = """
insert into address (
    postcode, street, street_fold, street_no, locality, municipality_id,
    search_key, latin_key, kaek, geom, source
)
select distinct on (s.municipality_id, s.street_fold, s.street_no)
    null, s.street, s.street_fold, s.street_no, s.locality, s.municipality_id,
    s.search_key, s.latin_key, s.kaek,
    st_setsrid(st_point(s.lon, s.lat), 4326)::geography, 'cosmote'
from stage_cosmote_address s
order by s.municipality_id, s.street_fold, s.street_no
on conflict (postcode, street_fold, street_no, municipality_id) do nothing
"""

STAGE_ANSWER = """
create temp table stage_cosmote (
    address_id bigint, technology text, max_down_mbps numeric,
    observed_at timestamp, plans text
) on commit drop
"""

STAGE_SCAN = """
create temp table stage_cosmote_scan (
    municipality_id int, street_fold text, scanned_to int
) on commit drop
"""

STAGE_RESOLVED = """
create temp table stage_cosmote_resolved (
    id bigint, municipality_id int, street_fold text
) on commit drop
"""

# so a probe can use the operator's spelling
RESOLVE = """
update raw_cosmote c
set municipality_id = r.municipality_id, street_fold = r.street_fold
from stage_cosmote_resolved r
where r.id = c.id
  and (c.municipality_id is distinct from r.municipality_id
    or c.street_fold is distinct from r.street_fold)
"""

# the scrape gave up after five misses in a row and only wrote down hits
MARK_SCANNED = """
update address a set checked_to = s.scanned_to
from (
    select municipality_id, street_fold, max(scanned_to) as scanned_to
    from stage_cosmote_scan group by municipality_id, street_fold
) s
where a.municipality_id = s.municipality_id and a.street_fold = s.street_fold
  and a.checked_to is distinct from s.scanned_to
"""

# the scrape only kept yeses. TTL by speed, same rule as the probes
CACHE = """
insert into availability (
    address_id, provider_id, technology, max_down_mbps, serviceable,
    source, assertion, observed_at, expires_at, raw
)
select distinct on (s.address_id)
    s.address_id, p.id, s.technology, s.max_down_mbps, true,
    'isp-live', 'declared',
    s.observed_at at time zone 'Europe/Athens',
    (s.observed_at at time zone 'Europe/Athens') + case
        when s.max_down_mbps >= %(gigabit)s then %(settled)s
        when s.max_down_mbps >= %(fast)s then %(likely)s
        when s.max_down_mbps >= %(usable)s then %(changing)s
        else %(volatile)s
    end,
    jsonb_build_object('plans', s.plans)
from stage_cosmote s
cross join (select id from provider where code = 'TELEKOM') p
order by s.address_id, s.observed_at desc, s.max_down_mbps desc, s.technology
on conflict (address_id, provider_id, technology) do update set
    max_down_mbps = excluded.max_down_mbps,
    serviceable = excluded.serviceable,
    source = excluded.source,
    assertion = excluded.assertion,
    observed_at = excluded.observed_at,
    expires_at = excluded.expires_at,
    raw = excluded.raw
-- a live answer newer than the scrape wins, and skip unchanged rows
where availability.observed_at <= excluded.observed_at
  and (availability.technology, availability.max_down_mbps, availability.serviceable,
       availability.source, availability.assertion, availability.observed_at,
       availability.expires_at, availability.raw)
      is distinct from
      (excluded.technology, excluded.max_down_mbps, excluded.serviceable,
       excluded.source, excluded.assertion, excluded.observed_at,
       excluded.expires_at, excluded.raw)
"""


def keys(street: str, locality: str | None) -> tuple[str, str, str]:
    # same as the register path
    k = street_key(street)
    search = f"{k} {fold(locality)}" if locality else k
    return k, search, from_greek(search)


def best_plan(plans: str, catalogue: dict[str, tuple[float, str]]) -> tuple[float, str] | None:
    # the top rung says what's in the ground, vectoring stops short of 200
    known = [catalogue[code] for code in plans.split(",") if code in catalogue]
    return max(known) if known else None


def add_addresses(conn: psycopg.Connection[TupleRow]) -> int:
    held = {(m, f, n) for m, f, n in conn.execute(HELD)}
    best: dict[tuple[int, str, str], tuple[int, tuple[object, ...]]] = {}

    after = 0
    while True:
        rows = conn.execute(PLACES, (after, CHUNK)).fetchall()
        if not rows:
            break
        for _, mid, street, no, area, precision, kaek, lon, lat in rows:
            folded, search, latin = keys(street, area)
            k = (mid, folded, str(no))
            if k in held:
                continue
            rank = PRECISION.get(precision, UNRANKED)
            if k in best and best[k][0] <= rank:
                continue
            best[k] = (rank, (mid, street, folded, str(no), area, search, latin, kaek, lon, lat))
        after = int(rows[-1][0])

    conn.execute(STAGE_ADDRESS)
    if best:
        with conn.cursor().copy(
            "copy stage_cosmote_address (municipality_id, street, street_fold, street_no, "
            "locality, search_key, latin_key, kaek, lon, lat) from stdin"
        ) as copy:
            for _, row in best.values():
                copy.write_row(row)
    return conn.execute(ADD_ADDRESS).rowcount


def cache_answers(conn: psycopg.Connection[TupleRow]) -> int:
    catalogue = {code: (float(mbps), tech) for code, mbps, tech in conn.execute(CATALOGUE).fetchall()}
    index = {
        (mid, f, no): aid
        for mid, f, no, aid in conn.execute(
            "select municipality_id, street_fold, street_no, id from address "
            "where municipality_id is not null and street_no is not null"
        )
    }

    conn.execute(STAGE_ANSWER)
    conn.execute(STAGE_SCAN)
    conn.execute(STAGE_RESOLVED)
    ceiling: dict[tuple[int, str], int] = {}
    written = 0
    after = 0
    while True:
        rows = conn.execute(ANSWERS, (after, CHUNK)).fetchall()
        if not rows:
            break
        staged: list[tuple[object, ...]] = []
        resolved: list[tuple[object, ...]] = []
        for rid, mid, street, no, plans, observed_at in rows:
            folded = street_key(street)
            # matched or not, the scan got this far
            ceiling[(mid, folded)] = max(ceiling.get((mid, folded), no), no)
            resolved.append((rid, mid, folded))
            aid = index.get((mid, folded, str(no)))
            if aid is None:
                continue
            best = best_plan(plans, catalogue)
            if best is None:
                continue
            mbps, tech = best
            staged.append((aid, tech, mbps, observed_at, plans))
        # whole chunk read before the copy, interleaving deadlocks on ClientRead
        if resolved:
            with conn.cursor().copy(
                "copy stage_cosmote_resolved (id, municipality_id, street_fold) from stdin"
            ) as copy:
                for row in resolved:
                    copy.write_row(row)
        if staged:
            with conn.cursor().copy(
                "copy stage_cosmote (address_id, technology, max_down_mbps, observed_at, "
                "plans) from stdin"
            ) as copy:
                for row in staged:
                    copy.write_row(row)
            written += len(staged)
        after = int(rows[-1][0])

    if ceiling:
        with conn.cursor().copy(
            "copy stage_cosmote_scan (municipality_id, street_fold, scanned_to) from stdin"
        ) as copy:
            for (mid, folded), top in ceiling.items():
                copy.write_row((mid, folded, top))
        conn.execute(MARK_SCANNED)

    conn.execute(RESOLVE)
    conn.execute(CACHE, {
        "gigabit": GIGABIT, "fast": FAST, "usable": USABLE,
        "settled": SETTLED, "likely": LIKELY, "changing": CHANGING, "volatile": VOLATILE,
    })
    return written


def build_cosmote(conn: psycopg.Connection[TupleRow]) -> int:
    conn.execute(AREA)
    conn.execute("create index on cosmote_area (dimos, area)")
    add_addresses(conn)
    return cache_answers(conn)
