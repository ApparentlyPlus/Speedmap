-- What a municipality looks like from far enough away to see all of it. One figure per
-- view, because the choropleth is drawn under whichever view is on.
truncate municipality_coverage;

-- The filed half. sold_mbps is the same anchor 110 uses, so a municipality and the streets
-- inside it cannot disagree. Fixed lines only, and every municipality: 80 have no address
-- filed and would otherwise be holes under a view that has something to say about them.
insert into municipality_coverage (municipality_id, addresses, fiber, best_mbps)
select m.id,
       count(a.id),
       count(*) filter (where cov.fiber),
       max(cov.mbps)
from municipality m
left join address a on a.municipality_id = m.id
left join lateral (
    select bool_or(ac.family = 'fiber') as fiber,
           max(t.sold_mbps) as mbps
    from address_coverage ac
    join technology t on t.code = ac.technology
    where ac.address_id = a.id
      and ac.family <> 'wireless'
) cov on true
group by m.id;

-- The measured half, weighted by tests rather than averaged over cells: one 900 Mbps cell
-- from two tests must not outvote forty 30 Mbps cells from five hundred each.
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
    join speed_cell c on st_contains(mu.geom_2d, c.geom::geometry)
    group by mu.id
) t
where t.id = mc.municipality_id;
