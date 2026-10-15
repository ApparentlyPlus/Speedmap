"""The tile layers as GeoJSON lines, built by Postgres so Python never holds 214k dicts."""

from __future__ import annotations

import gzip
import os
import pathlib
import tempfile

import psycopg
from psycopg.rows import TupleRow

from publish import fields

# below it streets drop id and nprov so tippecanoe merges them (z6 had 56,439 streets, 642 distinct)
DETAIL_FROM = 10

STREETS = """
with reach as (
    select sp.street_id, count(*) as nprov
           {aggregates}
    from street_provider sp
    join provider p on p.id = sp.provider_id
    group by sp.street_id
)
select json_build_object(
    'type', 'Feature',
    'tippecanoe', json_build_object('minzoom', {detail_from}),
    'geometry', st_asgeojson(st_transform(s.geom::geometry, 4326), 6)::json,
    'properties', json_build_object(
        'id', s.id,
        'best_mbps', s.best_mbps,
        'nprov', coalesce(r.nprov, 0)
        {operators}
    )
)::text
from street s
left join reach r on r.street_id = s.id
where s.geom is not null
-- draw order follows read order, unordered crossings swap between builds
order by s.id
"""

# below DETAIL_FROM. Slowest first so fast lines draw on top, identical ones adjacent
STREETS_OVERVIEW = """
with reach as (
    select sp.street_id
           {aggregates}
    from street_provider sp
    join provider p on p.id = sp.provider_id
    group by sp.street_id
),
drawn as (
    select s.id, s.best_mbps, s.geom,
           json_build_object('best_mbps', s.best_mbps {operators}) as properties
    from street s
    left join reach r on r.street_id = s.id
    where s.geom is not null
)
select json_build_object(
    'type', 'Feature',
    'tippecanoe', json_build_object('maxzoom', {detail_from} - 1),
    'geometry', st_asgeojson(st_transform(geom::geometry, 4326), 6)::json,
    'properties', properties
)::text
from drawn
order by best_mbps nulls first, properties::text, id
"""

REGION_SMOOTH = 0.0005

REGIONS = """
select json_build_object(
    'type', 'Feature',
    'geometry', st_asgeojson(
        st_simplifypreservetopology(m.geom_2d, {smooth}), 6
    )::json,
    'properties', json_build_object(
        'id', m.id,
        'name', m.name,
        'addresses', coalesce(mc.addresses, 0),
        'fiber', coalesce(mc.fiber, 0),
        -- 0 when nothing's filed, never null
        'fiber_share', case
            when coalesce(mc.addresses, 0) = 0 then 0
            else round(mc.fiber::numeric / mc.addresses, 4)
        end,
        'best_mbps', mc.best_mbps,
        'measured_mbps', round(mc.measured_mbps, 1),
        'measured_tests', mc.measured_tests,
        'mobile_mbps', round(mc.mobile_mbps, 1),
        'mobile_tests', mc.mobile_tests
    )
)::text
from municipality m
left join municipality_coverage mc on mc.municipality_id = m.id
where m.geom_2d is not null
order by m.id
"""


HALF_TILE = 40075016.686 / (1 << 16) / 2  # web mercator metres
SHORE = 0.02  # ~2 km offshore still counts

# only tested cells exist, so nothing's nullable. ~4% of Greece is tested
CELLS = """
with greece as (
    select st_buffer(st_union(geom::geometry), {shore}) as area from municipality
)
select json_build_object(
    'type', 'Feature',
    'geometry', st_asgeojson(
        st_transform(
            st_envelope(st_expand(st_transform(c.geom::geometry, 3857), {half})),
            4326
        ),
        6
    )::json,
    'properties', json_build_object(
        'quadkey', c.quadkey,
        'family', c.family,
        'down_mbps', c.avg_down_mbps,
        'up_mbps', c.avg_up_mbps,
        'tests', c.tests
    )
)::text
from (
    -- latest quarter only, or the squares stack up darker each quarter
    select distinct on (quadkey, family) *
    from speed_cell
    order by quadkey, family, observed_on desc
) c, greece g
where c.geom is not null
  and st_intersects(g.area, c.geom::geometry)
order by c.quadkey
"""


SERVED_UNFILED = -1  # reaches the street, no speed filed (49,897 pairs)


def aggregates() -> str:
    # one grouped pass, correlated subqueries were a million index probes
    return "".join(
        f", max(sp.mbps) filter (where p.code = '{code}') as {field}_mbps"
        f", count(*) filter (where p.code = '{code}') as {field}_n"
        for code, field in fields.STREETS_BY_PROVIDER.items()
    )


def operators() -> str:
    # null where the operator doesn't reach
    return "".join(
        f", '{field}', case when r.{field}_n > 0 "
        f"then coalesce(r.{field}_mbps, {SERVED_UNFILED}) end"
        for field in fields.STREETS_BY_PROVIDER.values()
    )


def write(conn: psycopg.Connection[TupleRow], sql: str, out: pathlib.Path) -> int:
    """Stream one layer to a temp file and rename it into place when done."""
    out.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    fd, name = tempfile.mkstemp(dir=out.parent, prefix=out.name + ".")
    tmp = pathlib.Path(name)
    try:
        # named cursor, so it streams server side
        with os.fdopen(fd, "w", encoding="utf-8") as f, conn.cursor(name="publish") as cur:
            cur.itersize = 5000
            cur.execute(sql)
            for (feature,) in cur:
                f.write(feature)
                f.write("\n")
                n += 1
        tmp.replace(out)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return n


def streets(conn: psycopg.Connection[TupleRow], out: pathlib.Path) -> int:
    sql = STREETS.format(aggregates=aggregates(), operators=operators(), detail_from=DETAIL_FROM)
    return write(conn, sql, out)


def streets_overview(conn: psycopg.Connection[TupleRow], out: pathlib.Path) -> int:
    sql = STREETS_OVERVIEW.format(aggregates=aggregates(), operators=operators(), detail_from=DETAIL_FROM)
    return write(conn, sql, out)


SMOOTH = 0.0002  # ~20 m
KNIT = 0.0015  # ~150 m, closes the slivers between municipalities

OUTLINE = """
select st_asgeojson(
    -- a self crossing ring triangulates into a slab over some island
    st_makevalid(
        st_simplifypreservetopology(st_buffer(st_union(geom::geometry), {knit}), {smooth})
    ),
    5
)
from municipality
"""


def outline(conn: psycopg.Connection[TupleRow], out: pathlib.Path) -> int:
    row = conn.execute(OUTLINE.format(knit=KNIT, smooth=SMOOTH)).fetchone()
    if row is None or row[0] is None:
        raise SystemExit("no municipalities: the country has no outline")
    out.parent.mkdir(parents=True, exist_ok=True)
    body = ('{"type":"Feature","properties":{},"geometry":' + row[0] + "}").encode("utf-8")
    # plus a .gz for Caddy's precompressed, 1.4 MB down to about a quarter
    for path, data in ((out, body), (out.with_name(out.name + ".gz"), gzip.compress(body, 9))):
        tmp = path.with_name(path.name + ".part")
        tmp.write_bytes(data)
        tmp.replace(path)
    return out.stat().st_size


def regions(conn: psycopg.Connection[TupleRow], out: pathlib.Path) -> int:
    return write(conn, REGIONS.format(smooth=REGION_SMOOTH), out)


def cells(conn: psycopg.Connection[TupleRow], out: pathlib.Path) -> int:
    return write(conn, CELLS.format(half=HALF_TILE, shore=SHORE), out)
