"""Build the searchable address index from the register's infrastructure points."""

from __future__ import annotations

from collections.abc import Iterator
from typing import cast

import psycopg
from psycopg.rows import TupleRow

from normalise.address import parse

# One point can carry several addresses and several points can share one address, so the
# rows are staged first and deduplicated in SQL rather than in Python memory.
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

# Resolve the municipality once, into the staging table, rather than inside both the merge
# and the link. Written as a select rather than an update: one pass, no dead tuples.
RESOLVE = """
create temp table stage_address on commit drop as
select s.*, m.id as municipality_id
from stage_raw s
left join municipality m on st_contains(m.geom_2d, st_setsrid(st_point(s.lon, s.lat), 4326))
"""

INDEX = "create index on stage_address (postcode, street_fold, street_no, municipality_id)"

# Read in keyset chunks rather than through a server-side cursor: a COPY and a FETCH
# cannot interleave on one connection, and the second one blocks forever.
SOURCE = """
select coverid, address, prempass, connstat, vhcn, st_x(point), st_y(point)
from raw_coverpoint
where point is not null and coverid > %s
order by coverid
limit %s
"""

CHUNK = 50_000

# distinct on, because on conflict cannot touch the same row twice in one statement.
# Ordering by premises keeps the best-attested version of a repeated address.
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
order by s.postcode, s.street_fold, s.street_no, s.municipality_id, s.premises desc nulls last, s.street
on conflict (postcode, street_fold, street_no, municipality_id) do update set
    street = excluded.street,
    locality = excluded.locality,
    search_key = excluded.search_key,
    latin_key = excluded.latin_key,
    premises = excluded.premises,
    connected = excluded.connected,
    vhcn = excluded.vhcn,
    geom = excluded.geom
"""

# psycopg hands back untyped tuples, so the shape of the select is declared here.
SourceRow = tuple[str, str, int | None, int | None, int | None, float, float]

StageRow = tuple[
    str, str | None, str, str, str | None, str | None, str, str,
    int | None, bool | None, bool | None, float, float,
]


def flag(value: int | None) -> bool | None:
    """The register writes these as 0/1; absent stays absent rather than becoming false."""
    return None if value is None else bool(value)


# is not distinct from, because postcode, street_no and municipality_id are all nullable
# and the address key treats nulls as equal.
LINK = """
insert into address_point (address_id, coverid)
select distinct a.id, s.coverid
from stage_address s
join address a
  on a.street_fold = s.street_fold
 and a.postcode is not distinct from s.postcode
 and a.street_no is not distinct from s.street_no
 and a.municipality_id is not distinct from s.municipality_id
on conflict do nothing
"""

# The distinct spellings, rebuilt with the index they are a projection of.
#
# Concurrently, so a rebuild never blanks the relation the search is reading — the same
# reason 090_wholesale.sql refreshes that way. It is what the fuzzy tier matches against
# instead of the 1.8M rows here; see migration 0048 and api/main.py's fuzzy_address_sql.
REFRESH_KEYS = "refresh materialized view concurrently address_spelling"

COPY_INTO = (
    "copy stage_raw (coverid, postcode, street, street_fold, street_no, locality, search_key, latin_key, "
    "premises, connected, vhcn, lon, lat) from stdin"
)


def staged(chunk: list[SourceRow]) -> Iterator[StageRow]:
    """Every address on every point in this chunk. One point may carry several."""
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
