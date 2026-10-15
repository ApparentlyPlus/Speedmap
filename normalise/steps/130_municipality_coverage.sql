-- one figure per municipality per view, for the choropleth
truncate municipality_coverage;

-- filed: same anchor as 110, fixed lines, every municipality (80 have no addresses)
insert into municipality_coverage (municipality_id, addresses, fiber, best_mbps)
select m.id,
       count(a.id),
       count(*) filter (where cov.fiber),
       max(cov.mbps)
from municipality m
left join address a on a.municipality_id = m.id
-- one pass and a hash join, not a lateral 1.8M times
left join (
    -- capped like 110, or ADSL towns read 24 while their streets read 10
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

-- measured, weighted by tests
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
    -- latest quarter only, speed_cell keeps them all
    join (
        select distinct on (quadkey, family) *
        from speed_cell
        order by quadkey, family, observed_on desc
    ) c on st_contains(mu.geom_2d, c.geom::geometry)
    group by mu.id
) t
where t.id = mc.municipality_id;
