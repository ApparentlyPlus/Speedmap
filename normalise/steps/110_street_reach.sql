-- Who reaches each street and how fast, by three routes: doors filed on it, cabinets it runs
-- through, built fiber next to it. Builders file doors and no polygons, and half the streets
-- have no door, so either of the first two alone loses a different half.
--
-- The figure is the line's retail speed (technology.sold_mbps), capped by what the operator
-- filed. The register can pull it down and never lift it. The cap is a4a_nordown, the normally
-- available speed. least() ignoring nulls is on purpose: no band, and the open-ended ">= 1000"
-- band, both mean no cap.
--
-- Fixed lines only. 5G reaches nearly every address and would paint the country one colour.
--
-- Every row found is kept in street_offer, one per street, operator and technology, and the
-- street panel reads it as is. street_provider, which paints the map, is derived from it
-- below, so the colour and the panel can't drift apart.
truncate street_offer, street_provider;

insert into street_offer (
    street_id, provider_id, technology, family, matched, avail_date, infra_provider_id,
    speed_band_id, sold_mbps
)
-- the fastest row for each, as the panel always listed it
select distinct on (src.street_id, src.provider_id, src.technology) src.*
from (
    select s.id as street_id, ac.provider_id, ac.technology, ac.family,
           'point' as matched, ac.avail_date, ac.infra_provider_id, ac.speed_band_id,
           least(t.sold_mbps, coalesce(nb.max_mbps, sb.max_mbps)) as sold_mbps
    from street s
    -- 065's pin, not the name: by name, every component of a name would get the filings of all
    -- the others, the bleeding the component split exists to stop
    join address a on a.street_id = s.id
    join address_coverage ac on ac.address_id = a.id
    join technology t on t.code = ac.technology
    left join speed_band sb on sb.id = ac.speed_band_id
    left join speed_band nb on nb.id = ac.normal_band_id
    where ac.family <> 'wireless'

    union all

    -- Cabinet-sized areas only. The big filings are exchange regions and say nothing about one
    -- street. cabinet_m2() is the same cut the API uses.
    select s.id, ca.provider_id, ca.technology, ca.family,
           'area', ca.avail_date, ca.infra_provider_id, ca.speed_band_id,
           least(t.sold_mbps, coalesce(nb.max_mbps, sb.max_mbps))
    from street s
    join coverage_area ca on st_intersects(ca.geom_2d, s.geom::geometry)
    join technology t on t.code = ca.technology
    left join speed_band sb on sb.id = ca.speed_band_id
    left join speed_band nb on nb.id = ca.normal_band_id
    where ca.family <> 'wireless'
      and ca.area_m2 <= cabinet_m2()

    union all

    -- Fiber the register placed but never addressed.
    --
    -- Route one assumes the filing named an address. 307,300 builder filings name no street
    -- and no number, and 025 only rescues those standing near a door the index holds. Rural
    -- Greece has few: Πύλου-Νέστορος has 4,789 fiber points and 50 addresses, so its villages
    -- drew as copper with the fiber sitting in the road.
    --
    -- OSM is dense exactly where the address index is thin, so these are placed against street
    -- geometry. 463,418 premises passed were invisible before this, 371,097 of them Telekom's.
    --
    -- Only the nearest street. A point passing fifty premises fronts more than one road and
    -- the filing doesn't say which, so the one it stands on is all the data supports. How near
    -- is built_fiber_m(), which the provenance invariant reads too.
    select near.id, coalesce(p.credited_to, p.id), 'FTTH', 'fiber',
           'built', null::date, coalesce(p.credited_to, p.id), null::int, t.sold_mbps
    from raw_coverpoint c
    join provider p on p.register_id = c.infrprov
    join technology t on t.code = 'FTTH'
    cross join lateral (
        select st.id
        from street st
        where st_dwithin(st.geom, c.point::geography, built_fiber_m())
        order by st.geom <-> c.point::geography, st.id
        limit 1
    ) near
    where c.prempass > 0
      and p.builds_own_network
      and c.point is not null
      -- Only points with no door on a street, since those reach their street by route one. A
      -- door 065 couldn't pin reaches nothing that way: 624,750 builder points sat on such
      -- doors, on no street at all, and fiber streets got painted as copper.
      and not exists (
          select 1
          from address_point ap
          join address a on a.id = ap.address_id
          where ap.coverid = c.coverid and a.street_id is not null
      )
) src
-- every column, so which of two equally fast rows the panel shows is stable across builds
order by src.street_id, src.provider_id, src.technology, src.sold_mbps desc nulls last,
         src.matched, src.speed_band_id desc nulls last, src.infra_provider_id nulls last,
         src.avail_date nulls last, src.family;

insert into street_provider (street_id, provider_id, mbps)
select street_id, provider_id, max(sold_mbps)
from street_offer
group by street_id, provider_id;
