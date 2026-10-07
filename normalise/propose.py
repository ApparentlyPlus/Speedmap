"""Make an address the register never filed, because someone asked for it.

The register holds 1.8M addresses and the street layer the streets they're on, and the two
disagree: a street can be known while most of its numbers aren't.
"""

from __future__ import annotations

import re

import psycopg
from psycopg.rows import TupleRow

from normalise.greeklish import from_greek
from normalise.text import fold

# The postcode and locality most of the street's doors share. Skips doors 065 pinned to
# another road of the same name. Matching by name alone picked up every road of that name
# in the municipality, and the new door got the postcode and position of one across town.
# Unpinned doors of the name still count.
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

# the neighbour nearest in numbering, and its point
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

# the same two lookups every other address gets, for one point
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
-- one band per cell and it's 5G's, so 4G gets none where both are flagged
cross join lateral (
    select 'FWA_5G' as technology, nullif(g.maxdown, 0) as band where g.tech5gf = 1
    union all
    select 'FWA_4G', case when g.tech5gf = 1 then null else nullif(g.maxdown, 0) end
    where g.tech4gf = 1
) gen
order by c.id, coalesce(sp.credited_to, sp.id), gen.technology, g.maxdown desc nulls last
on conflict (address_id, provider_id, technology) do nothing
"""


# where most of the street's doors say they are, as 066 does for every street
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
    """The id of the address at this number on this street, made if it's new.

    Keyed like the register load, so asking twice returns the same address.
    """
    found = conn.execute(STREET, (street_id,)).fetchone()
    if found is None:
        return None
    name, folded, municipality, midpoint = found

    near = conn.execute(
        NEIGHBOURS, {"fold": folded, "municipality": municipality, "street_id": street_id}
    ).fetchone()
    postcode, locality = (near[0], near[1]) if near is not None else (None, None)

    digits = re.match(r"^\d+", street_no)
    anchor = conn.execute(NEAREST, {
        "fold": folded, "municipality": municipality, "street_id": street_id,
        "number": int(digits.group()) if digits else 0,
    }).fetchone()
    # the street's midpoint, only when it has no filed address to stand next to
    geom = midpoint if anchor is None else anchor[0]

    key = folded if locality is None else f"{folded} {fold(locality)}"
    fields = {
        "street": name, "fold": folded, "number": street_no,
        "locality": locality, "postcode": postcode, "municipality": municipality,
        "key": key, "latin": from_greek(key), "geom": geom,
        # known here, no need for 065: someone asked for this number on this street
        "street_id": street_id,
    }

    row = conn.execute(INSERT, fields).fetchone()
    if row is None:
        held = conn.execute(EXISTING, fields).fetchone()
        return None if held is None else int(held[0])

    address_id = int(row[0])
    conn.execute(COVER_AREA, (address_id,))
    conn.execute(COVER_CELL, (address_id,))
    # the build stores the street's locality, and a new door may shift it
    conn.execute(LOCALITY, (street_id, street_id))
    return address_id
