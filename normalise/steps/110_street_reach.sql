-- Who reaches each street and how fast, from both routes: the doors filed on it and the
-- cabinets it runs through. Builders file doors and no polygons, half the streets have no
-- door at all, so asking only one of the two loses a different half each way.
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
    -- every component of a name the filings of all the others, which is the bleeding the
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
) src
group by src.street_id, src.provider_id;
