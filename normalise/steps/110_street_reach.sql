-- Who reaches each street and how fast, from three routes: the doors filed on it, the
-- cabinets it runs through, and the built fiber standing next to it. Builders file doors
-- and no polygons, half the streets have no door at all, so asking only one of the first
-- two loses a different half each way.
--
-- The figure is what the line is retailed at (technology.sold_mbps), capped by what the
-- operator filed for it. The register can only pull it down, never lift it.
--
-- The cap is a4a_nordown, the normally available speed, not the maximum. least() ignoring
-- nulls is deliberate: no band, and the open-ended ">= 1000" band, both mean "no cap".
--
-- Fixed lines only. 5G reaches nearly every address and would paint the country one colour.
truncate street_provider;

insert into street_provider (street_id, provider_id, mbps)
select src.street_id, src.provider_id, max(src.mbps)
from (
    select s.id as street_id, ac.provider_id, least(t.sold_mbps, coalesce(nb.max_mbps, sb.max_mbps)) as mbps
    from street s
    -- The pin 065 worked out, rather than the name. Matching on the name here would hand
    -- every component of a name the filings of all the others. That bleeding is what the
    -- split into components exists to stop.
    join address a on a.street_id = s.id
    join address_coverage ac on ac.address_id = a.id
    join technology t on t.code = ac.technology
    left join speed_band sb on sb.id = ac.speed_band_id
    left join speed_band nb on nb.id = ac.normal_band_id
    where ac.family <> 'wireless'

    union all

    -- Cabinet-sized areas only: the big filings are exchange regions and say nothing about
    -- one street. cabinet_m2() is the same cut api/main.py makes.
    select s.id, ca.provider_id, least(t.sold_mbps, coalesce(nb.max_mbps, sb.max_mbps))
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
    -- The first route reaches a street through an address, which assumes the filing named
    -- one. 307,300 builder filings name no street and no number, and 025 can only rescue
    -- the ones standing near a door the address index happens to hold. In rural Greece it
    -- does not hold many: Πύλου-Νέστορος has 4,789 fiber points and 50 addresses in the
    -- whole municipality, so its villages drew as copper while the fiber sat in the road.
    --
    -- OSM is dense exactly where the address index is thin, so these filings are placed
    -- against street geometry instead, skipping the address layer that has nothing to say
    -- about them. 463,418 premises passed were invisible this way, 371,097 of them
    -- Telekom's.
    --
    -- The nearest street, and only the nearest. A point passing fifty premises fronts onto
    -- more than one road and the filing never says which, so the one it is standing on is
    -- the only claim the data supports. How near it has to stand is built_fiber_m(), which
    -- the invariant checking where a figure came from reads too.
    select near.id, coalesce(p.credited_to, p.id), t.sold_mbps
    from raw_coverpoint c
    join provider p on p.register_id = c.infrprov
    join technology t on t.code = 'FTTH'
    cross join lateral (
        select st.id
        from street st
        where st_dwithin(st.geom, c.point::geography, built_fiber_m())
        order by st.geom <-> c.point::geography
        limit 1
    ) near
    where c.prempass > 0
      and p.builds_own_network
      and c.point is not null
      -- Only what no address could be found for. A filing already on a door reaches its
      -- street through the door, and saying it twice changes nothing but the runtime.
      and not exists (select 1 from address_point ap where ap.coverid = c.coverid)
) src
group by src.street_id, src.provider_id;
