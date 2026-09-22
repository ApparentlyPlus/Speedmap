"""An address the register never filed, made because someone asked for it.

The register holds 1.8M addresses and the street layer holds the streets they sit on, and
the two do not agree: a street can be known while most of its numbers are not.
"""

from __future__ import annotations

import re

import psycopg
from psycopg.rows import TupleRow

from normalise.greeklish import from_greek
from normalise.text import fold

# The postcode and locality a street's known addresses agree on.
NEIGHBOURS = """
select a.postcode, a.locality, count(*) as seen
from address a
where a.street_fold = %(fold)s
  and a.municipality_id is not distinct from %(municipality)s
group by a.postcode, a.locality
order by seen desc, a.postcode nulls last
limit 1
"""

STREET = """
select s.name, s.name_fold, s.municipality_id,
       st_lineinterpolatepoint(st_geometryn(s.geom::geometry, 1), 0.5)::geography
from street s where s.id = %s
"""

# The neighbour nearest in numbering, and its point.
NEAREST = """
select a.geom
from address a
where a.street_fold = %(fold)s
  and a.municipality_id is not distinct from %(municipality)s
  and a.geom is not null
order by abs(
    coalesce(substring(a.street_no from '^[0-9]+')::int, 0) - %(number)s
), a.id
limit 1
"""

INSERT = """
insert into address (
    street, street_fold, street_no, locality, postcode,
    municipality_id, search_key, latin_key, geom, source, street_id
)
values (
    %(street)s, %(fold)s, %(number)s, %(locality)s, %(postcode)s,
    %(municipality)s, %(key)s, %(latin)s, %(geom)s, 'asked', %(street_id)s
)
on conflict (postcode, street_fold, street_no, municipality_id) do nothing
returning id
"""

EXISTING = """
select id from address
where street_fold = %(fold)s and street_no = %(number)s
  and municipality_id is not distinct from %(municipality)s
  and postcode is not distinct from %(postcode)s
"""

# The same two lookups every other address gets, run for one point.
COVER_AREA = """
insert into address_coverage (
    address_id, provider_id, technology, infra_provider_id,
    speed_band_id, family, matched_by, avail_date
)
select distinct on (ca.provider_id, ca.technology)
       a.id, ca.provider_id, ca.technology, ca.infra_provider_id,
       ca.speed_band_id, ca.family, 'area', ca.avail_date
from address a
join coverage_area ca on st_contains(ca.geom_2d, a.geom::geometry)
where a.id = %s
order by ca.provider_id, ca.technology, ca.avail_date nulls last
on conflict (address_id, provider_id, technology) do nothing
"""

COVER_CELL = """
with cell as (
    select a.id, floor(st_x(p.g) / 100)::int || '|' || floor(st_y(p.g) / 100)::int as gridid
    from address a
    cross join lateral (select st_transform(a.geom::geometry, 2100) as g) p
    where a.id = %s
)
insert into address_coverage (
    address_id, provider_id, technology, infra_provider_id,
    speed_band_id, family, matched_by
)
select distinct on (c.id, sp.id)
    c.id, sp.id,
    case when g.tech5gf = 1 then 'FWA_5G' else 'FWA_4G' end,
    ip.id, nullif(g.maxdown, 0), 'wireless', 'cell'
from cell c
join raw_wireless_grid g on g.gridid = c.gridid
join provider sp on sp.register_id = g.servprov
left join provider ip on ip.register_id = g.infrprov
where g.tech4gf = 1 or g.tech5gf = 1
order by c.id, sp.id, g.tech5gf desc, g.maxdown desc nulls last
on conflict (address_id, provider_id, technology) do nothing
"""


def propose(
    conn: psycopg.Connection[TupleRow], street_id: int, street_no: str
) -> int | None:
    """The id of the address at this number on this street, creating it if it is new.

    Idempotent by the same unique key the register load uses, so asking twice returns the same
    address rather than a second one.
    """
    found = conn.execute(STREET, (street_id,)).fetchone()
    if found is None:
        return None
    name, folded, municipality, midpoint = found

    near = conn.execute(
        NEIGHBOURS, {"fold": folded, "municipality": municipality}
    ).fetchone()
    postcode, locality = (near[0], near[1]) if near is not None else (None, None)

    digits = re.match(r"^\d+", street_no)
    anchor = conn.execute(NEAREST, {
        "fold": folded, "municipality": municipality,
        "number": int(digits.group()) if digits else 0,
    }).fetchone()
    # Half way along the street only when the street has no filed address at all to stand by.
    geom = midpoint if anchor is None else anchor[0]

    key = folded if locality is None else f"{folded} {fold(locality)}"
    fields = {
        "street": name, "fold": folded, "number": street_no,
        "locality": locality, "postcode": postcode, "municipality": municipality,
        "key": key, "latin": from_greek(key), "geom": geom,
        # Known outright here rather than worked out by 065: this address exists because
        # somebody asked for it on this street, so there is nothing to infer.
        "street_id": street_id,
    }

    row = conn.execute(INSERT, fields).fetchone()
    if row is None:
        held = conn.execute(EXISTING, fields).fetchone()
        return None if held is None else int(held[0])

    address_id = int(row[0])
    conn.execute(COVER_AREA, (address_id,))
    conn.execute(COVER_CELL, (address_id,))
    return address_id
