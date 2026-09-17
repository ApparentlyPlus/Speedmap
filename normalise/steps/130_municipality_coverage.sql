-- What a municipality looks like from far enough away to see all of it.
--
-- Runs after every source of coverage, including the builders of step 100: three operators
-- retail their own fibre and file no service at all, and a municipality of theirs would
-- otherwise read as having none.
--
-- One figure per view, because the choropleth is drawn under whichever view is on and a
-- filed claim under a measured map is the one mixture this site does not make. See
-- migration 0050.
truncate municipality_coverage;

-- The filed half.
--
-- best_mbps is what the best line into the address is sold at — technology.sold_mbps, the
-- same anchor 110 paints streets with, so a municipality and the streets inside it cannot
-- disagree. They did, and in two ways: this step clamped to max_plausible_mbps where 110
-- did not, and it wrote the clamp as `least(coalesce(sb.max_mbps, sb.min_mbps),
-- t.max_plausible_mbps)` — where `least(null, 24)` is 24 in Postgres, so every unfiled ADSL
-- row was quietly worth 24 Mbps. Both go with the band.
--
-- Fixed lines only, the same rule the streets follow. 5G reaches nearly every address in
-- the country, and a figure counting it is a figure about Greece rather than about a
-- municipality.
--
-- Fibre share rather than the fastest anything is what the layer actually paints: 124
-- municipalities have no fibre at all and 77 have it almost everywhere, and that is the
-- thing that varies.
-- Every municipality, not every one with a filed address. 80 of the 333 have none — and
-- every one of those 80 has speed tests in it, so keyed on addresses they came out as 80
-- holes in the country under a view that had something to say about all of them. A hole
-- reads as a broken layer rather than as a quiet one.
insert into municipality_coverage (municipality_id, addresses, fibre, best_mbps)
select m.id,
       count(a.id),
       count(*) filter (where seen.fibre),
       max(seen.mbps)
from municipality m
left join address a on a.municipality_id = m.id
left join lateral (
    select bool_or(ac.family = 'fibre') as fibre,
           max(t.sold_mbps) as mbps
    from address_coverage ac
    join technology t on t.code = ac.technology
    where ac.address_id = a.id
      and ac.family <> 'wireless'
) seen on true
group by m.id;

-- The measured half, both families.
--
-- Weighted by tests rather than averaged over cells. A municipality with one cell of
-- 900 Mbps from two tests and forty cells of 30 Mbps from five hundred each is a 30 Mbps
-- municipality; the plain mean calls it 50, and the choropleth then paints the outlier.
--
-- Only about four per cent of the country has ever been tested, so most municipalities come
-- out null under one family or both. That is the normal case and the layer draws it as
-- unmeasured rather than as nought.
--
-- Joined on the cell's point against the municipality's own outline, which is what the rest
-- of the site means by Greece. A cell whose centre falls offshore belongs to no
-- municipality and is simply not counted here; the tile builder gives it two kilometres of
-- slack because it is drawing a square, and this is counting, not drawing.
update municipality_coverage mc
set measured_mbps = m.fixed_mbps,
    measured_tests = m.fixed_tests,
    mobile_mbps = m.mobile_mbps,
    mobile_tests = m.mobile_tests
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
) m
where m.id = mc.municipality_id;
