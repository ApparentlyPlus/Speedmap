"""The two tile layers, as newline-delimited GeoJSON.

Postgres builds the JSON and COPY streams it out, so 214,000 features never become 214,000
Python dictionaries on the way to a file.
"""

from __future__ import annotations

import os
import pathlib
import tempfile

import psycopg
from psycopg.rows import TupleRow

from publish import fields

# One row per street, with each operator's best under the field the contract names it.
# The pivot is generated so that adding an operator is a schema edit, not a SQL edit.
STREETS = """
select json_build_object(
    'type', 'Feature',
    'geometry', st_asgeojson(st_transform(s.geom::geometry, 4326), 6)::json,
    'properties', json_build_object(
        'id', s.id,
        'best_mbps', s.best_mbps,
        'nprov', (select count(*) from street_provider sp where sp.street_id = s.id)
        {operators}
    )
)::text
from street s
where s.geom is not null
-- Ordered, because tippecanoe writes features out in the order it reads them and the
-- renderer draws them in that order. Without it Postgres may hand back the same rows in a
-- different sequence on the next build, and two streets that cross swap which one is on top.
-- That is how a rebuild with no data change still moved several hundred pixels.
order by s.id
"""

# One feature per municipality, for the zooms where a street is a fraction of a pixel.
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
        'fibre', coalesce(mc.fibre, 0),
        -- Nought to one, and nought when nothing is filed rather than null: the ramp this
        -- is painted by is a share, and a share of no addresses is not a speed nobody knows,
        -- it is a municipality the register has not described.
        'fibre_share', case
            when coalesce(mc.addresses, 0) = 0 then 0
            else round(mc.fibre::numeric / mc.addresses, 4)
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


# Half a zoom 16 tile, in Web Mercator metres.
HALF_TILE = 40075016.686 / (1 << 16) / 2

# How far past the coastline a cell may sit and still be Greek, in degrees: about two kilometres.
SHORE = 0.02

# Only tested cells exist, and the figure is the reason the cell is there, so nothing here is
# nullable. Greece is about four per cent tested: an empty view is the normal case.
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
from speed_cell c, greece g
where c.geom is not null
  and st_intersects(g.area, c.geom::geometry)
order by c.quadkey
"""


# An operator that reaches a street and filed no speed for it, which 49,897 street-operator pairs
# are.
SERVED_UNFILED = -1


def operators() -> str:
    """The per-operator columns, named by the contract rather than by this file."""
    return "".join(
        f", '{field}', (select coalesce(max(sp.mbps), {SERVED_UNFILED}) "
        f"from street_provider sp join provider p on p.id = sp.provider_id "
        f"where sp.street_id = s.id and p.code = '{code}' having count(*) > 0)"
        for code, field in fields.STREETS_BY_PROVIDER.items()
    )


def write(conn: psycopg.Connection[TupleRow], sql: str, out: pathlib.Path) -> int:
    """Stream one layer to a file, and only then give it its name.

    A build that dies half way through leaves the temporary file behind and the previous
    layer untouched, rather than a renderer reading half of one.
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
            # Server side, so a layer is streamed rather than assembled in memory first.
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
    return write(conn, STREETS.format(operators=operators()), out)


# How much the coastline is smoothed, in degrees: about twenty metres.
SMOOTH = 0.0002

# Enough to close the slivers between one municipality and the next without moving the coast
# anywhere a reader would notice: about a hundred and fifty metres.
KNIT = 0.0015

# The country itself, as one polygon. The land is published and the sea is not, which is the way
# round that works.
OUTLINE = """
select st_asgeojson(
    -- Valid, because a ring that crosses itself triangulates into whatever the renderer
    -- makes of it, and what it makes of it is a slab over somebody's island.
    st_makevalid(
        st_simplifypreservetopology(st_buffer(st_union(geom::geometry), {knit}), {smooth})
    ),
    5
)
from municipality
"""


def outline(conn: psycopg.Connection[TupleRow], out: pathlib.Path) -> int:
    """The country, written as one GeoJSON feature."""
    row = conn.execute(OUTLINE.format(knit=KNIT, smooth=SMOOTH)).fetchone()
    if row is None or row[0] is None:
        raise SystemExit("no municipalities: the country has no outline")
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".part")
    tmp.write_text(
        '{"type":"Feature","properties":{},"geometry":' + row[0] + "}",
        encoding="utf-8",
    )
    tmp.replace(out)
    return out.stat().st_size


def regions(conn: psycopg.Connection[TupleRow], out: pathlib.Path) -> int:
    return write(conn, REGIONS.format(smooth=REGION_SMOOTH), out)


def cells(conn: psycopg.Connection[TupleRow], out: pathlib.Path) -> int:
    return write(conn, CELLS.format(half=HALF_TILE, shore=SHORE), out)
