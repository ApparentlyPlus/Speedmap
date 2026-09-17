"""The two tile layers, as newline-delimited GeoJSON.

Postgres builds the JSON and COPY streams it out, so 214,000 features never become 214,000
Python dictionaries on the way to a file. The field names come from the generated contract
rather than from string literals here: that is the whole point of generating them, and a
builder that spells one its own way is exactly the drift the contract exists to stop.

Written to a temporary path and moved into place, because a tile build that dies half way
through must not leave a renderer reading half a layer.
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
"""

# One feature per municipality, for the zooms where a street is a fraction of a pixel.
#
# The contract has declared this layer since the schema was written and nothing ever built
# it: schema/tiles.yaml named it, publish/fields.py and web/src/map/tiles.ts were generated
# from it, 130_municipality_coverage.sql computed municipality_coverage to feed it, and the
# archive came out with two layers where three were promised. Below zoom 10 the map drew a
# coastline and nothing inside it.
#
# Every municipality, not every one with a filed address. 80 of the 333 have none at all,
# and left to an inner join they come out as holes in the country — which reads as a broken
# layer rather than as a quiet one. They are drawn with a null figure and no share, which is
# what the register actually says about them.
#
# Simplified, because these are administrative boundaries drawn to the metre and nobody
# reading a choropleth at zoom 6 is looking at the coastline: about fifty metres, which is
# under a pixel at the zooms this layer is for.
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
"""


# Half a zoom 16 tile, in Web Mercator metres. Ookla publish the centroid; a square is what
# was measured, and drawn as a point it becomes a dot whose size means nothing — a tested
# street and a tested suburb look the same.
#
# Expanded in Mercator rather than on the ground, because that is the grid the tile is cut
# on: 611 m of Mercator is 611·cos(latitude) of ground, so a Greek tile covers about 464 m
# and not the 600 m the figure is usually quoted as.
HALF_TILE = 40075016.686 / (1 << 16) / 2

# How far past the coastline a cell may sit and still be Greek, in degrees: about two
# kilometres. Ookla's grid is square and the coast is not, so a cell covering a seafront
# street has its centre offshore. Without the slack the map loses the promenade of every
# island it has measurements for, which is most of the ones anybody asks about.
SHORE = 0.02

# Only tested cells exist, and the figure is the reason the cell is there, so nothing here
# is nullable. Greece is about four per cent tested: an empty view is the normal case.
#
# Clipped to the country. The measurements arrive as a bounding box around Greece, and that
# box contains Istanbul, Sofia, Tirana and Skopje — half of every cell on file is a street
# this site has nothing to say about. The municipalities are the border: they are already
# here, they are what the rest of the site means by Greece, and unioning them agrees with
# the coverage register by construction in a way a separately fetched outline would not.
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
"""


# An operator that reaches a street and filed no speed for it, which 49,897 street-operator
# pairs are. It has to be told apart from an operator that does not reach the street at all:
# both are an absent number, and only one of them should be drawn when the map is filtered
# to that operator. So reaching without a speed is one below the bottom of the ramp — where
# the ramp already paints "not filed" — and not reaching stays null.
#
# The `having` is what makes the difference expressible: over no rows the whole subquery
# yields null, while over a row with a null speed it yields the sentinel.
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
    written = 0
    descriptor, name = tempfile.mkstemp(dir=out.parent, prefix=out.name + ".")
    staged = pathlib.Path(name)
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
                written += 1
        staged.replace(out)
    except BaseException:
        staged.unlink(missing_ok=True)
        raise
    return written


def streets(conn: psycopg.Connection[TupleRow], out: pathlib.Path) -> int:
    return write(conn, STREETS.format(operators=operators()), out)


# How much the coastline is smoothed, in degrees: about twenty metres. Small enough that a
# harbour is still a harbour at the zoom anyone looks at one, large enough that the outline
# is a file a phone downloads rather than a map of every rock.
SMOOTH = 0.0002

# Enough to close the slivers between one municipality and the next without moving the coast
# anywhere a reader would notice: about a hundred and fifty metres.
KNIT = 0.0015

# The country itself, as one polygon.
#
# The land is published and the sea is not, which is the way round that works. Painting the
# sea instead needs a polygon with the country cut out of it, and a hole-ridden ring that
# size is cut into tiles before it is drawn and clips so badly that whole tiles come out
# filled — rectangular slabs of land across the Aegean, and coastlines that are tile edges.
#
# Drawn from underneath, none of that can happen: what is not Greece is simply not drawn,
# and the background is already the sea.
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
    staged = out.with_suffix(out.suffix + ".part")
    staged.write_text(
        '{"type":"Feature","properties":{},"geometry":' + row[0] + "}",
        encoding="utf-8",
    )
    staged.replace(out)
    return out.stat().st_size


def regions(conn: psycopg.Connection[TupleRow], out: pathlib.Path) -> int:
    return write(conn, REGIONS.format(smooth=REGION_SMOOTH), out)


def cells(conn: psycopg.Connection[TupleRow], out: pathlib.Path) -> int:
    return write(conn, CELLS.format(half=HALF_TILE, shore=SHORE), out)
