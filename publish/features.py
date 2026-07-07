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

# Half a zoom 16 tile, in Web Mercator metres. Ookla publish the centroid; a square is what
# was measured, and drawn as a point it becomes a dot whose size means nothing — a tested
# street and a tested suburb look the same.
#
# Expanded in Mercator rather than on the ground, because that is the grid the tile is cut
# on: 611 m of Mercator is 611·cos(latitude) of ground, so a Greek tile covers about 464 m
# and not the 600 m the figure is usually quoted as.
HALF_TILE = 40075016.686 / (1 << 16) / 2

# Only tested cells exist, and the figure is the reason the cell is there, so nothing here
# is nullable. Greece is about four per cent tested: an empty view is the normal case.
CELLS = """
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
from speed_cell c
where c.geom is not null
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


def cells(conn: psycopg.Connection[TupleRow], out: pathlib.Path) -> int:
    return write(conn, CELLS.format(half=HALF_TILE), out)
