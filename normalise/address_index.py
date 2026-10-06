"""Build the searchable address index from the register's infrastructure points."""

from __future__ import annotations

from collections.abc import Iterator
from typing import cast

import psycopg
from psycopg.rows import TupleRow

from normalise.address import parse

# A point can carry several addresses and several points can share one, so rows are staged
# and deduplicated in SQL instead of Python memory.
STAGE = """
create temp table stage_raw (
    coverid text,
    postcode text,
    street text,
    street_fold text,
    street_no text,
    locality text,
    search_key text,
    latin_key text,
    premises int,
    connected boolean,
    vhcn boolean,
    lon double precision,
    lat double precision
) on commit drop
"""

# Resolve the municipality once, into staging, for both the merge and the link. A select
# instead of an update: one pass, no dead tuples.
RESOLVE = """
create temp table stage_address on commit drop as
select s.*, m.id as municipality_id
from stage_raw s
left join municipality m on st_contains(m.geom_2d, st_setsrid(st_point(s.lon, s.lat), 4326))
"""

INDEX = "create index on stage_address (postcode, street_fold, street_no, municipality_id)"

# Keyset chunks, no server-side cursor: a COPY and a FETCH can't interleave on one
# connection, and the second blocks forever.
SOURCE = """
select coverid, address, prempass, connstat, vhcn, st_x(point), st_y(point)
from raw_coverpoint
where point is not null and coverid > %s
order by coverid
limit %s
"""

CHUNK = 50_000

# distinct on, since on conflict can't touch one row twice in a statement. Highest premises
# wins, as the best-attested version of a repeated address.
MERGE = """
insert into address (
    postcode, street, street_fold, street_no, locality, search_key, latin_key,
    premises, connected, vhcn, geom, municipality_id
)
select distinct on (s.postcode, s.street_fold, s.street_no, s.municipality_id)
    s.postcode, s.street, s.street_fold, s.street_no, s.locality, s.search_key, s.latin_key,
    s.premises, s.connected, s.vhcn,
    st_point(s.lon, s.lat)::geography, s.municipality_id
from stage_address s
order by s.postcode, s.street_fold, s.street_no, s.municipality_id, s.premises desc nulls last, s.street,
         -- coverid last, so the same register always builds the same index
         s.coverid
on conflict (postcode, street_fold, street_no, municipality_id) do update set
    street = excluded.street,
    locality = excluded.locality,
    search_key = excluded.search_key,
    latin_key = excluded.latin_key,
    premises = excluded.premises,
    connected = excluded.connected,
    vhcn = excluded.vhcn,
    geom = excluded.geom
-- Only rows that changed. Rewriting all 1.47M addresses touched every index, two trigram
-- ones included, and was most of the build's slowest step.
where (address.street, address.locality, address.search_key, address.latin_key,
       address.premises, address.connected, address.vhcn, address.geom)
      is distinct from
      (excluded.street, excluded.locality, excluded.search_key, excluded.latin_key,
       excluded.premises, excluded.connected, excluded.vhcn, excluded.geom)
"""

# psycopg returns untyped tuples, so the row shapes are declared here
SourceRow = tuple[str, str, int | None, int | None, int | None, float, float]

StageRow = tuple[
    str, str | None, str, str, str | None, str | None, str, str,
    int | None, bool | None, bool | None, float, float,
]


def flag(value: int | None) -> bool | None:
    """0/1 from the register. Missing stays None, never False."""
    return None if value is None else bool(value)


# is not distinct from, since postcode, street_no and municipality_id can be null and the
# address key treats nulls as equal.
#
# Filings with an empty field (`,,`, mostly postcode only) are skipped. 025 places them by
# position and deletes any link made here, so linking them wrote 1.9M rows a build just to
# be deleted again. Same pattern as 025, character for character.
LINK = """
insert into address_point (address_id, coverid)
select distinct a.id, s.coverid
from stage_address s
join raw_coverpoint c on c.coverid = s.coverid
join address a
  on a.street_fold = s.street_fold
 and a.postcode is not distinct from s.postcode
 and a.street_no is not distinct from s.street_no
 and a.municipality_id is not distinct from s.municipality_id
where c.address !~ ',[[:space:]]*,'
on conflict do nothing
"""

# the distinct spellings, rebuilt with the index they project
REFRESH_KEYS = "refresh materialized view concurrently address_spelling"

COPY_INTO = (
    "copy stage_raw (coverid, postcode, street, street_fold, street_no, locality, search_key, latin_key, "
    "premises, connected, vhcn, lon, lat) from stdin"
)


def staged(chunk: list[SourceRow]) -> Iterator[StageRow]:
    """Every address on every point in the chunk. A point can carry several."""
    for coverid, raw, premises, connstat, vhcn, lon, lat in chunk:
        for address in parse(raw):
            yield (
                coverid,
                address.postcode,
                address.street,
                address.street_fold,
                address.street_no,
                address.locality,
                address.search_key,
                address.latin_key,
                premises,
                flag(connstat),
                flag(vhcn),
                lon,
                lat,
            )


def build_address_index(conn: psycopg.Connection[TupleRow]) -> int:
    conn.execute(STAGE)
    cursor = ""
    while True:
        chunk = cast(list[SourceRow], conn.execute(SOURCE, (cursor, CHUNK)).fetchall())
        if not chunk:
            break
        with conn.cursor().copy(COPY_INTO) as copy:
            for row in staged(chunk):
                copy.write_row(row)
        cursor = chunk[-1][0]

    conn.execute(RESOLVE)
    conn.execute(INDEX)
    written = conn.execute(MERGE).rowcount
    conn.execute(LINK)
    conn.execute(REFRESH_KEYS)
    return written
