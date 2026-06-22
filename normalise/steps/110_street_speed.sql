-- After every source of coverage is in, including the builders who retail their own fibre
-- and file nothing: those are step 100, and a street of theirs would otherwise read as
-- having no speed at all.
-- The topmost band is open-ended and files no ceiling, so its floor stands in for it.
update street s
set best_mbps = best.mbps
from (
    select a.municipality_id, a.street_fold,
           max(coalesce(sb.max_mbps, sb.min_mbps)) as mbps
    from address a
    join address_coverage ac on ac.address_id = a.id
    join speed_band sb on sb.id = ac.speed_band_id
    group by a.municipality_id, a.street_fold
) best
where best.municipality_id = s.municipality_id
  and best.street_fold = s.name_fold
  and s.best_mbps is distinct from best.mbps;
