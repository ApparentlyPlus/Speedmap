"""Group OSM ways into streets, one row per named road per municipality."""

from __future__ import annotations

from collections.abc import Iterator
from typing import cast

import psycopg
from psycopg.rows import TupleRow

from normalise.greeklish import from_greek
from normalise.text import street_key

STAGE = """
create temp table stage_street (
    osm_id bigint primary key,
    name_fold text,
    latin_key text,
    sort_key text
) on commit drop
"""

SOURCE = "select osm_id, name from raw_osm_street"

# array_agg ordered by the same key on every column, so the stored name, its fold and its
# latin form all come from one way rather than from three different ones.
MERGE = """
insert into street (
    name, name_fold, latin_key, sort_key, municipality_id, highway, ways, geom
)
select
    (array_agg(r.name order by r.name, r.osm_id))[1],
    (array_agg(s.name_fold order by r.name, r.osm_id))[1],
    (array_agg(s.latin_key order by r.name, r.osm_id))[1],
    s.sort_key,
    m.id,
    mode() within group (order by r.highway),
    count(*),
    st_multi(st_union(r.geom))::geography
from stage_street s
join raw_osm_street r on r.osm_id = s.osm_id
left join municipality m on st_contains(m.geom_2d, st_centroid(r.geom))
group by s.sort_key, m.id
on conflict (sort_key, municipality_id) do update set
    name = excluded.name,
    name_fold = excluded.name_fold,
    latin_key = excluded.latin_key,
    highway = excluded.highway,
    ways = excluded.ways,
    geom = excluded.geom
"""

# A road removed from the extract must leave, and its id must not be reused by another.
PRUNE = """
delete from street st
where not exists (
    select 1 from stage_street s
    join raw_osm_street r on r.osm_id = s.osm_id
    where s.sort_key = st.sort_key
)
"""

StageRow = tuple[int, str, str, str]


def keyed(rows: list[tuple[int, str]]) -> Iterator[StageRow]:
    for osm_id, name in rows:
        fold = street_key(name)
        yield osm_id, fold, from_greek(fold), " ".join(sorted(fold.split()))


def build_street_index(conn: psycopg.Connection[TupleRow]) -> int:
    conn.execute(STAGE)
    # Read before the copy opens: a select and a copy cannot share one connection, and the
    # copy would sit waiting for rows the select cannot deliver.
    source = cast(list[tuple[int, str]], conn.execute(SOURCE).fetchall())
    with conn.cursor().copy(
        "copy stage_street (osm_id, name_fold, latin_key, sort_key) from stdin"
    ) as copy:
        for row in keyed(source):
            copy.write_row(row)
    written = conn.execute(MERGE).rowcount
    conn.execute(PRUNE)
    return written
