"""Group OSM ways into streets: one row per connected run of a named road per municipality."""

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

# How far apart two pieces of road may be and still be the same street, in degrees. About
# 55 m at Greek latitudes. That steps over a square, a roundabout or the central reservation
# of a dual carriageway. Two roads a block apart stay two roads.
#
# The rule is transitive, which is what makes it work on a long road: a road is a chain of
# ways, and each link only has to reach the next one.
NEAR_DEGREES = 0.0005

# One row per connected run, keyed so a rebuild lands on the same rows it did last time.
#
# The cluster numbers ST_ClusterDBSCAN hands out depend on the order it read the ways in,
# and that order is not promised. They are thrown away and replaced by a rank over the
# westernmost point of each run, so the same OSM extract always produces the same components
# under the same numbers, and therefore the same street ids.
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
-- Where each run begins, worked out here rather than inside the rank below: a window
-- function may not appear in another window function's order by.
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

# array_agg ordered by the same key on every column, so the stored name, its fold and its
# latin form all come from one way rather than from three different ones.
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

# A road removed from the extract must leave, and so must a run that has since joined the
# one next to it: a component number that is no longer produced is no longer a street.
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
    conn.execute(GROUPED, {"near": NEAR_DEGREES})
    written = conn.execute(MERGE).rowcount
    conn.execute(PRUNE)
    return written
