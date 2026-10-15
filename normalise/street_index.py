"""OSM ways grouped into streets, one per connected run of a name in a municipality."""

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

# ~55 m here, steps over a square or a central reservation but not a block
NEAR_DEGREES = 0.0005

# dbscan numbers by read order, rank by westernmost point instead for stable ids
GROUPED = """
create temp table stage_group on commit drop as
with placed as (
    select s.sort_key, m.id as municipality_id, r.osm_id, r.name, r.highway, r.geom,
           s.name_fold, s.latin_key
    from stage_street s
    join raw_osm_street r on r.osm_id = s.osm_id
    left join municipality m on st_contains(m.geom_2d, st_centroid(r.geom))
),
clustered as (
    select placed.*,
           st_clusterdbscan(geom, eps => %(near)s::float8, minpoints => 1)
             over (partition by sort_key, municipality_id) as run
    from placed
),
-- can't nest a window in another's order by
anchored as (
    select clustered.*,
           min(st_xmin(geom)) over w as run_x,
           min(st_ymin(geom)) over w as run_y
    from clustered
    window w as (partition by sort_key, municipality_id, run)
),
ordered as (
    select anchored.*,
           dense_rank() over (
               partition by sort_key, municipality_id
               order by run_x, run_y, run
           ) - 1 as component
    from anchored
)
select sort_key, municipality_id, component,
       (array_agg(name order by name, osm_id))[1] as name,
       (array_agg(name_fold order by name, osm_id))[1] as name_fold,
       (array_agg(latin_key order by name, osm_id))[1] as latin_key,
       mode() within group (order by highway) as highway,
       count(*)::int as ways,
       st_multi(st_union(geom))::geography as geom
from ordered
group by sort_key, municipality_id, component
"""

MERGE = """
insert into street (
    name, name_fold, latin_key, sort_key, municipality_id, component, highway, ways, geom
)
select name, name_fold, latin_key, sort_key, municipality_id, component, highway, ways, geom
from stage_group
on conflict (sort_key, municipality_id, component) do update set
    name = excluded.name,
    name_fold = excluded.name_fold,
    latin_key = excluded.latin_key,
    highway = excluded.highway,
    ways = excluded.ways,
    geom = excluded.geom
"""

# gone from the extract, or merged into a neighbour
PRUNE = """
delete from street st
where not exists (
    select 1 from stage_group g
    where g.sort_key = st.sort_key
      and g.municipality_id is not distinct from st.municipality_id
      and g.component = st.component
)
"""

StageRow = tuple[int, str, str, str]


def keyed(rows: list[tuple[int, str]]) -> Iterator[StageRow]:
    for osm_id, name in rows:
        k = street_key(name)
        yield osm_id, k, from_greek(k), " ".join(sorted(k.split()))


def build_street_index(conn: psycopg.Connection[TupleRow]) -> int:
    conn.execute(STAGE)
    # fetch everything before the copy starts, they can't share the connection
    rows = cast(list[tuple[int, str]], conn.execute(SOURCE).fetchall())
    with conn.cursor().copy("copy stage_street (osm_id, name_fold, latin_key, sort_key) from stdin") as copy:
        for row in keyed(rows):
            copy.write_row(row)
    conn.execute(GROUPED, {"near": NEAR_DEGREES})
    n = conn.execute(MERGE).rowcount
    conn.execute(PRUNE)
    return n
