-- Runs after every source of coverage, including the builders of step 100: three operators
-- retail their own fibre and file no service at all, and a municipality of theirs would
-- otherwise read as having none.
--
-- best_mbps is held to what the technology can physically carry, the same clamp the ranker
-- applies. The register files 942 services above their ceiling, five of them ADSL at a
-- gigabit, and an unclamped maximum paints half the country its best colour.
truncate municipality_coverage;

insert into municipality_coverage (municipality_id, addresses, fibre, best_mbps)
select a.municipality_id,
       count(*),
       count(*) filter (where seen.fibre),
       max(seen.mbps)
from address a
cross join lateral (
    select bool_or(ac.family = 'fibre') as fibre,
           max(least(coalesce(sb.max_mbps, sb.min_mbps), t.max_plausible_mbps)) as mbps
    from address_coverage ac
    join technology t on t.code = ac.technology
    left join speed_band sb on sb.id = ac.speed_band_id
    where ac.address_id = a.id
) seen
where a.municipality_id is not null
group by a.municipality_id;
