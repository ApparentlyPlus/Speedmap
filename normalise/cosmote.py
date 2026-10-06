"""Fold the Telekom availability scrape into the address index and the answer cache.

The scrape walked house numbers up from the start of each street and stopped after five
numbers in a row with no service.
"""

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

# Which of two filings of one address to keep. Most rows were geocoded by interpolating
# along the street. A rooftop is a real building, so it wins.
PRECISION = {"rooftop": 0, "interpolated": 1, "street": 2, "locality": 3}
UNRANKED = len(PRECISION)

# Their dimoi aren't Καλλικράτης ones and the names don't resolve. Street names repeat
# nationwide, so voting on names maps almost nothing. We place each area by its points.
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

# Only the rungs the scrape's codes name. Unlimited airtime quotes no speed, so it can't say
# what a scraped code was worth.
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

# the scrape has no postcodes
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

# kept so a probe can use the operator's own spelling of the street
RESOLVE = """
update raw_cosmote c
set municipality_id = r.municipality_id, street_fold = r.street_fold
from stage_cosmote_resolved r
where r.id = c.id
  and (c.municipality_id is distinct from r.municipality_id
    or c.street_fold is distinct from r.street_fold)
"""

# The ceiling is the last number the scrape recorded, up to five short of the last it
# asked: the ones in between were refused and never written down.
MARK_SCANNED = """
update address a set checked_to = s.scanned_to
from (
    select municipality_id, street_fold, max(scanned_to) as scanned_to
    from stage_cosmote_scan group by municipality_id, street_fold
) s
where a.municipality_id = s.municipality_id and a.street_fold = s.street_fold
  -- only where it moved, or every build rewrites a million addresses with what they hold
  and a.checked_to is distinct from s.scanned_to
"""

# The scrape only recorded serviceable answers, so serviceable is always true. How long each
# is trusted depends on the speed, using the probe loop's rule.
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
-- The scrape is one day's snapshot. A live answer since then is newer, and every rebuild
-- used to overwrite it with the scrape.
where availability.observed_at <= excluded.observed_at
  -- skip unchanged rows too, or a build rewrites a million answers with themselves
  and (availability.technology, availability.max_down_mbps, availability.serviceable,
       availability.source, availability.assertion, availability.observed_at,
       availability.expires_at, availability.raw)
      is distinct from
      (excluded.technology, excluded.max_down_mbps, excluded.serviceable,
       excluded.source, excluded.assertion, excluded.observed_at,
       excluded.expires_at, excluded.raw)
"""


def keys(street: str, locality: str | None) -> tuple[str, str, str]:
    """street_fold, search_key and latin_key, built the same way as the register path."""
    folded = street_key(street)
    search = f"{folded} {fold(locality)}" if locality else folded
    return folded, search, from_greek(search)


def best_plan(plans: str, catalogue: dict[str, tuple[float, str]]) -> tuple[float, str] | None:
    """The fastest plan offered here, which names the technology.

    Vectored copper stops short of 200 Mbps, so the top rung says what's in the ground. An
    unknown code is skipped: a new one means the catalogue changed.
    """
    known = [catalogue[code] for code in plans.split(",") if code in catalogue]
    return max(known) if known else None


def add_addresses(conn: psycopg.Connection[TupleRow]) -> int:
    """Addresses the operator serves that the register never filed."""
    held = {(m, f, n) for m, f, n in conn.execute(HELD)}
    best: dict[tuple[int, str, str], tuple[int, tuple[object, ...]]] = {}

    after = 0
    while True:
        read = conn.execute(PLACES, (after, CHUNK)).fetchall()
        if not read:
            break
        for _, municipality_id, street, street_no, area, precision, kaek, lon, lat in read:
            folded, search, latin = keys(street, area)
            key = (municipality_id, folded, str(street_no))
            if key in held:
                continue
            rank = PRECISION.get(precision, UNRANKED)
            if key in best and best[key][0] <= rank:
                continue
            best[key] = (rank, (
                municipality_id, street, folded, str(street_no), area,
                search, latin, kaek, lon, lat,
            ))
        after = int(read[-1][0])

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
    """The answers, plus how far up each street the asking reached."""
    catalogue = {
        code: (float(mbps), technology)
        for code, mbps, technology in conn.execute(CATALOGUE).fetchall()
    }
    index = {
        (municipality_id, street_fold, street_no): address_id
        for municipality_id, street_fold, street_no, address_id in conn.execute(
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
        read = conn.execute(ANSWERS, (after, CHUNK)).fetchall()
        if not read:
            break
        staged: list[tuple[object, ...]] = []
        resolved: list[tuple[object, ...]] = []
        for row_id, municipality_id, street, street_no, plans, observed_at in read:
            folded = street_key(street)
            # every row raises the ceiling, matched or not, since the scan got that far
            reached = ceiling.get((municipality_id, folded), street_no)
            ceiling[(municipality_id, folded)] = max(reached, street_no)
            resolved.append((row_id, municipality_id, folded))
            address_id = index.get((municipality_id, folded, str(street_no)))
            if address_id is None:
                continue
            best = best_plan(plans, catalogue)
            if best is None:
                continue
            mbps, technology = best
            staged.append((address_id, technology, mbps, observed_at, plans))
        # Read the whole chunk before opening the copy. A select and a copy can't share one
        # connection, and interleaving them deadlocks on ClientRead.
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
        after = int(read[-1][0])

    if ceiling:
        with conn.cursor().copy(
            "copy stage_cosmote_scan (municipality_id, street_fold, scanned_to) from stdin"
        ) as copy:
            for (municipality_id, folded), scanned_to in ceiling.items():
                copy.write_row((municipality_id, folded, scanned_to))
        conn.execute(MARK_SCANNED)

    conn.execute(RESOLVE)
    # Thresholds come from the probe loop so a scraped gigabit and a probed one are both
    # trusted for two years.
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
