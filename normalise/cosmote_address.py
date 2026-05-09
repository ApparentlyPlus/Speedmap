"""Add the addresses the operator serves that the register never filed.

Keys are built exactly as the register path builds them, so a scraped address is found by
the same search as any other. Without this the streets in the 168 municipalities the
register leaves empty are answerable but unfindable.
"""

from __future__ import annotations

import psycopg
from psycopg.rows import TupleRow

from normalise.greeklish import from_greek
from normalise.text import fold, street_key

CHUNK = 50_000

# Which of two filings of one address to keep. The scrape geocoded most rows by
# interpolating along a street; a rooftop is an actual building and wins.
PRECISION = {"rooftop": 0, "interpolated": 1, "street": 2, "locality": 3}
UNRANKED = len(PRECISION)

HELD = """
select municipality_id, street_fold, street_no
from address
where municipality_id is not null and street_no is not null
"""

READ = """
select c.id, x.municipality_id, c.street, c.street_no, c.area, c.geocode_precision, c.kaek,
       st_x(c.geom::geometry), st_y(c.geom::geometry)
from raw_cosmote c
join cosmote_area x on x.dimos = c.dimos and x.area = coalesce(c.area, '')
where c.geom is not null and c.id > %s
order by c.id
limit %s
"""

STAGE = """
create temp table stage_cosmote_address (
    municipality_id int,
    street text,
    street_fold text,
    street_no text,
    locality text,
    search_key text,
    latin_key text,
    kaek text,
    lon double precision,
    lat double precision
) on commit drop
"""

# Postcode is absent from the scrape, so these rows carry none. The unique key treats nulls
# as equal, which is why an address already held under a postcode is filtered out in Python
# rather than left to collide here.
MERGE = """
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


def keys(street: str, locality: str | None) -> tuple[str, str, str]:
    """street_fold, search_key and latin_key, built as the register path builds them."""
    folded = street_key(street)
    search = f"{folded} {fold(locality)}" if locality else folded
    return folded, search, from_greek(search)


def build_cosmote_address(conn: psycopg.Connection[TupleRow]) -> int:
    held = {(m, f, n) for m, f, n in conn.execute(HELD)}
    best: dict[tuple[int, str, str], tuple[int, tuple[object, ...]]] = {}

    after = 0
    while True:
        read = conn.execute(READ, (after, CHUNK)).fetchall()
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

    conn.execute(STAGE)
    if best:
        with conn.cursor().copy(
            "copy stage_cosmote_address (municipality_id, street, street_fold, street_no, "
            "locality, search_key, latin_key, kaek, lon, lat) from stdin"
        ) as copy:
            for _, row in best.values():
                copy.write_row(row)
    return conn.execute(MERGE).rowcount
