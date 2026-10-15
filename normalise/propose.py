"""Make an address the register never filed, because someone asked for it."""

from __future__ import annotations

import re

import psycopg
from psycopg.rows import TupleRow

from normalise.greeklish import from_greek
from normalise.text import fold

# skip doors 065 pinned to another road with the same name across town
SAME_ROAD = """
a.street_fold = %(fold)s
  and a.municipality_id is not distinct from %(municipality)s
  and (a.street_id = %(street_id)s or a.street_id is null)
"""

NEIGHBOURS = f"""
select a.postcode, a.locality, count(*) as seen
from address a
where {SAME_ROAD}
group by a.postcode, a.locality
order by seen desc, a.postcode nulls last
limit 1
"""

STREET = """
select s.name, s.name_fold, s.municipality_id,
       st_lineinterpolatepoint(st_geometryn(s.geom::geometry, 1), 0.5)::geography
from street s where s.id = %s
"""

NEAREST = f"""
select a.geom
from address a
where {SAME_ROAD}
  and a.geom is not null
order by (a.street_id is not null) desc, abs(
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

COVER_AREA = """
insert into address_coverage (
    address_id, provider_id, technology, infra_provider_id,
    speed_band_id, normal_band_id, family, matched_by, avail_date
)
select distinct on (ca.provider_id, ca.technology)
       a.id, ca.provider_id, ca.technology, ca.infra_provider_id,
       ca.speed_band_id, ca.normal_band_id, ca.family, 'area', ca.avail_date
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
select distinct on (c.id, coalesce(sp.credited_to, sp.id), gen.technology)
    c.id, coalesce(sp.credited_to, sp.id), gen.technology,
    coalesce(ip.credited_to, ip.id), gen.band, 'wireless', 'cell'
from cell c
join raw_wireless_grid g on g.gridid = c.gridid
join provider sp on sp.register_id = g.servprov
left join provider ip on ip.register_id = g.infrprov
-- the cell's one band is 5G's when both are flagged
cross join lateral (
    select 'FWA_5G' as technology, nullif(g.maxdown, 0) as band where g.tech5gf = 1
    union all
    select 'FWA_4G', case when g.tech5gf = 1 then null else nullif(g.maxdown, 0) end
    where g.tech4gf = 1
) gen
order by c.id, coalesce(sp.credited_to, sp.id), gen.technology, g.maxdown desc nulls last
on conflict (address_id, provider_id, technology) do nothing
"""

# like 066 for one street
LOCALITY = """
update street s
set locality = (
    select mode() within group (order by a.locality)
    from address a
    where a.street_id = %s and a.locality is not null
)
where s.id = %s
"""


def propose(conn: psycopg.Connection[TupleRow], street_id: int, street_no: str) -> int | None:
    """Id of the address at this number on this street, made if it's new."""
    st = conn.execute(STREET, (street_id,)).fetchone()
    if st is None:
        return None
    name, folded, municipality, midpoint = st

    near = conn.execute(
        NEIGHBOURS, {"fold": folded, "municipality": municipality, "street_id": street_id}
    ).fetchone()
    postcode, locality = (near[0], near[1]) if near is not None else (None, None)

    digits = re.match(r"^\d+", street_no)
    anchor = conn.execute(NEAREST, {
        "fold": folded, "municipality": municipality, "street_id": street_id,
        "number": int(digits.group()) if digits else 0,
    }).fetchone()
    # stand next to the nearest number, midpoint if there are none
    geom = midpoint if anchor is None else anchor[0]

    key = folded if locality is None else f"{folded} {fold(locality)}"
    fields = {
        "street": name, "fold": folded, "number": street_no,
        "locality": locality, "postcode": postcode, "municipality": municipality,
        "key": key, "latin": from_greek(key), "geom": geom,
        "street_id": street_id,
    }

    row = conn.execute(INSERT, fields).fetchone()
    if row is None:
        held = conn.execute(EXISTING, fields).fetchone()
        return None if held is None else int(held[0])

    aid = int(row[0])
    conn.execute(COVER_AREA, (aid,))
    conn.execute(COVER_CELL, (aid,))
    conn.execute(LOCALITY, (street_id, street_id))  # a new door may shift it
    return aid
