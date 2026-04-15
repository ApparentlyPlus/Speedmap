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
create temp table stage_address (
    postcode text,
    street text,
    street_no text,
    locality text,
    search_key text,
    premises int,
    connected boolean,
    vhcn boolean,
    lon double precision,
    lat double precision
) on commit drop
"""

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
    postcode, street, street_no, locality, search_key,
    premises, connected, vhcn, geom, municipality_id
)
select distinct on (s.postcode, s.street, s.street_no, m.id)
    s.postcode, s.street, s.street_no, s.locality, s.search_key,
    s.premises, s.connected, s.vhcn,
    st_point(s.lon, s.lat)::geography, m.id
from stage_address s
left join municipality m on st_contains(m.geom_2d, st_setsrid(st_point(s.lon, s.lat), 4326))
order by s.postcode, s.street, s.street_no, m.id, s.premises desc nulls last
on conflict (postcode, street, street_no, municipality_id) do update set
    locality = excluded.locality,
    search_key = excluded.search_key,
    premises = excluded.premises,
    connected = excluded.connected,
    vhcn = excluded.vhcn,
    geom = excluded.geom
"""

# psycopg hands back untyped tuples, so the shape of the select is declared here.
SourceRow = tuple[str, str, int | None, int | None, int | None, float, float]

StageRow = tuple[
    str | None, str, str | None, str | None, str,
    int | None, bool | None, bool | None, float, float,
]


def flag(value: int | None) -> bool | None:
    """The register writes these as 0/1; absent stays absent rather than becoming false."""
    return None if value is None else bool(value)


COPY_INTO = (
    "copy stage_address (postcode, street, street_no, locality, search_key, "
    "premises, connected, vhcn, lon, lat) from stdin"
)


def staged(chunk: list[SourceRow]) -> Iterator[StageRow]:
    """Every address on every point in this chunk. One point may carry several."""
    for _, raw, premises, connstat, vhcn, lon, lat in chunk:
        for address in parse(raw):
            yield (
                address.postcode,
                address.street,
                address.street_no,
                address.locality,
                address.search_key,
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
    return conn.execute(MERGE).rowcount
