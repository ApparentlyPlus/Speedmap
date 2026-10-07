"""The tile layers as newline-delimited GeoJSON.

Postgres builds the JSON and COPY streams it out, so 214,000 features never become 214,000
Python dicts on the way to a file.
"""

from __future__ import annotations

import gzip
import os
import pathlib
import tempfile

import psycopg
from psycopg.rows import TupleRow

from publish import fields

# One row per street, each operator's best under the field name the contract gives it. The
# pivot is generated, so adding an operator is a schema edit. It's one grouped pass over
# street_provider, hash-joined: twelve correlated subqueries per street came to a million
# index probes over 80,000 streets.
# Streets carry their own id from DETAIL_FROM up, where one can be clicked and lit. Below
# it a street is under a pixel wide, and one z6 tile held 56,439 of them as separate features
# with only 642 distinct sets of attributes between them: the browser triangulated and styled
# every one. Down there they're written without id and nprov, ordered so identical ones sit
# together, and tippecanoe merges each run into one feature. The colour and every operator
# field survive, so the map looks and filters the same.
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
-- Ordered, because tippecanoe writes features in the order it reads them and the renderer
-- draws them in that order. Unordered, Postgres can return them differently next build, and
-- two crossing streets swap which is on top. A rebuild with no data change once moved
-- several hundred pixels that way.
order by s.id
"""

# The same streets for the zooms below DETAIL_FROM, without id and nprov. Slowest first, so
# the faster lines draw on top, and identical attribute sets come out next to each other for
# tippecanoe to merge. Tied on everything else, the street id keeps the order stable.
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

# one feature per municipality, for zooms where a street is a fraction of a pixel
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
        -- 0 to 1, and 0 when nothing is filed, never null. It's a share, and a share of no
        -- addresses means the register hasn't described the place.
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


HALF_TILE = 40075016.686 / (1 << 16) / 2  # half a zoom 16 tile, in Web Mercator metres

# how far past the coast a cell can sit and still count as Greek, in degrees (about 2 km)
SHORE = 0.02

# Only tested cells exist and the figure is why they're there, so nothing is nullable. About
# 4% of Greece is tested, so an empty view is normal.
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
    -- One square per tile and family, the latest quarter. Every quarter is kept, and drawing
    -- them all stacks a copy per quarter, each darker than the last.
    select distinct on (quadkey, family) *
    from speed_cell
    order by quadkey, family, observed_on desc
) c, greece g
where c.geom is not null
  and st_intersects(g.area, c.geom::geometry)
order by c.quadkey
"""


# an operator that reaches a street with no speed filed (49,897 street-operator pairs)
SERVED_UNFILED = -1


def aggregates() -> str:
    """Each operator's best, and whether it reaches at all: two columns per field."""
    return "".join(
        f", max(sp.mbps) filter (where p.code = '{code}') as {field}_mbps"
        f", count(*) filter (where p.code = '{code}') as {field}_n"
        for code, field in fields.STREETS_BY_PROVIDER.items()
    )


def operators() -> str:
    """The per-operator columns, named by the contract.

    Null where the operator doesn't reach, SERVED_UNFILED where it reaches with no speed.
    """
    return "".join(
        f", '{field}', case when r.{field}_n > 0 "
        f"then coalesce(r.{field}_mbps, {SERVED_UNFILED}) end"
        for field in fields.STREETS_BY_PROVIDER.values()
    )


def write(conn: psycopg.Connection[TupleRow], sql: str, out: pathlib.Path) -> int:
    """Stream one layer to a file, renaming it into place only when complete.

    A build that dies halfway leaves its temp file behind and the previous layer intact, so no
    renderer ever reads half of one.
    """
    out.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    descriptor, name = tempfile.mkstemp(dir=out.parent, prefix=out.name + ".")
    tmp = pathlib.Path(name)
    try:
        with (
            os.fdopen(descriptor, "w", encoding="utf-8") as handle,
            conn.cursor(name="publish") as cursor,
        ):
            # server-side, so the layer streams instead of building up in memory
            cursor.itersize = 5000
            cursor.execute(sql)
            for (feature,) in cursor:
                handle.write(feature)
                handle.write("\n")
                count += 1
        tmp.replace(out)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return count


def streets(conn: psycopg.Connection[TupleRow], out: pathlib.Path) -> int:
    sql = STREETS.format(aggregates=aggregates(), operators=operators(), detail_from=DETAIL_FROM)
    return write(conn, sql, out)


def streets_overview(conn: psycopg.Connection[TupleRow], out: pathlib.Path) -> int:
    sql = STREETS_OVERVIEW.format(aggregates=aggregates(), operators=operators(), detail_from=DETAIL_FROM)
    return write(conn, sql, out)


SMOOTH = 0.0002  # coastline smoothing, in degrees (about 20 m)

# Closes the slivers between neighbouring municipalities without moving the coast anywhere
# you'd notice: about 150 m.
KNIT = 0.0015

# The country as one polygon. We publish the land and not the sea, which is the way round
# that works.
OUTLINE = """
select st_asgeojson(
    -- Made valid: a self-crossing ring triangulates into whatever the renderer makes of it,
    -- which turned out to be a slab over somebody's island.
    st_makevalid(
        st_simplifypreservetopology(st_buffer(st_union(geom::geometry), {knit}), {smooth})
    ),
    5
)
from municipality
"""


def outline(conn: psycopg.Connection[TupleRow], out: pathlib.Path) -> int:
    """The country as a single GeoJSON feature."""
    row = conn.execute(OUTLINE.format(knit=KNIT, smooth=SMOOTH)).fetchone()
    if row is None or row[0] is None:
        raise SystemExit("no municipalities: the country has no outline")
    out.parent.mkdir(parents=True, exist_ok=True)
    body = ('{"type":"Feature","properties":{},"geometry":' + row[0] + "}").encode("utf-8")
    # A gzip copy beside it for Caddy's precompressed: 1.4 MB of coordinates, fetched on every
    # page open before the first tile, compress to about a quarter.
    for path, data in ((out, body), (out.with_name(out.name + ".gz"), gzip.compress(body, 9))):
        tmp = path.with_name(path.name + ".part")
        tmp.write_bytes(data)
        tmp.replace(path)
    return out.stat().st_size


def regions(conn: psycopg.Connection[TupleRow], out: pathlib.Path) -> int:
    return write(conn, REGIONS.format(smooth=REGION_SMOOTH), out)


def cells(conn: psycopg.Connection[TupleRow], out: pathlib.Path) -> int:
    return write(conn, CELLS.format(half=HALF_TILE, shore=SHORE), out)
