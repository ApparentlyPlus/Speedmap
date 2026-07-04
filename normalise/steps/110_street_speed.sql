-- After every source of coverage is in, including the builders who retail their own fibre
-- and file nothing: those are step 100, and a street of theirs would otherwise read as
-- having no speed at all.
-- The topmost band is open-ended and files no ceiling, so its floor stands in for it.
--
-- Mobile is left out, and that is the whole difference between a map and a flat colour.
-- 5G reaches nearly every address in the country, files a 300-1000 band wherever it does,
-- and so made 40,775 of the 40,796 streets that have a figure at all come out at exactly
-- 1000: one number, one colour, no information. What a street is asking about is the line
-- that runs down it.
update street s
set best_mbps = best.mbps
from (
    select a.municipality_id, a.street_fold,
           max(coalesce(sb.max_mbps, sb.min_mbps)) as mbps
    from address a
    join address_coverage ac on ac.address_id = a.id
    join speed_band sb on sb.id = ac.speed_band_id
    where ac.family <> 'wireless'
    group by a.municipality_id, a.street_fold
) best
where best.municipality_id = s.municipality_id
  and best.street_fold = s.name_fold
  and s.best_mbps is distinct from best.mbps;
