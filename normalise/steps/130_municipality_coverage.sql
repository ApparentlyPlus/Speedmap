-- A municipality seen from far enough away to see all of it. One figure per view, since the
-- choropleth sits under whichever view is on.
truncate municipality_coverage;

-- The filed half. sold_mbps is 110's anchor too, so a municipality can't disagree with its
-- streets. Fixed lines only, for every municipality: 80 have no address filed and would
-- otherwise be holes.
insert into municipality_coverage (municipality_id, addresses, fiber, best_mbps)
select m.id,
       count(a.id),
       count(*) filter (where cov.fiber),
       max(cov.mbps)
from municipality m
left join address a on a.municipality_id = m.id
-- each address's lines aggregated in one pass and hash-joined, not a lateral run 1.8M times
left join (
    -- Capped by the filing like 110. Uncapped, a municipality of 2-10 Mbps ADSL cabinets read
    -- 24 while every street in it read 10.
    select ac.address_id,
           bool_or(ac.family = 'fiber') as fiber,
           max(least(t.sold_mbps, coalesce(nb.max_mbps, sb.max_mbps))) as mbps
    from address_coverage ac
    join technology t on t.code = ac.technology
    left join speed_band sb on sb.id = ac.speed_band_id
    left join speed_band nb on nb.id = ac.normal_band_id
    where ac.family <> 'wireless'
    group by ac.address_id
) cov on cov.address_id = a.id
group by m.id;

-- The measured half, weighted by tests: one 900 Mbps cell from two tests mustn't outvote
-- forty 30 Mbps cells from five hundred each.
update municipality_coverage mc
set measured_mbps = t.fixed_mbps,
    measured_tests = t.fixed_tests,
    mobile_mbps = t.mobile_mbps,
    mobile_tests = t.mobile_tests
from (
    select mu.id,
           sum(c.avg_down_mbps * c.tests) filter (where c.family = 'fixed')
             / nullif(sum(c.tests) filter (where c.family = 'fixed'), 0) as fixed_mbps,
           sum(c.tests) filter (where c.family = 'fixed') as fixed_tests,
           sum(c.avg_down_mbps * c.tests) filter (where c.family = 'mobile')
             / nullif(sum(c.tests) filter (where c.family = 'mobile'), 0) as mobile_mbps,
           sum(c.tests) filter (where c.family = 'mobile') as mobile_tests
    from municipality mu
    -- Latest quarter per tile. speed_cell keeps every quarter, and summing across them counted
    -- a tile's tests once per quarter loaded.
    join (
        select distinct on (quadkey, family) *
        from speed_cell
        order by quadkey, family, observed_on desc
    ) c on st_contains(mu.geom_2d, c.geom::geometry)
    group by mu.id
) t
where t.id = mc.municipality_id;
