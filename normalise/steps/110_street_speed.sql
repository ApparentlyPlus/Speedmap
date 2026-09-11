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
-- Cleared first, so the step recomputes rather than fills in.
--
-- Both statements below only ever write a figure, so a street that qualified under a looser
-- rule keeps what that rule gave it forever and tightening anything here changes nothing.
-- That is how 3,189 streets went on being painted from district-wide filings after those
-- filings stopped being allowed to name a street.
update street set best_mbps = null where best_mbps is not null;

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

-- Then the streets with no doors on them at all.
--
-- A street's figure is the best of the addresses along it, and only 40,798 of the 80,756
-- streets have an address filed on them at all. The other half are lanes the register never
-- listed a door on, which are still streets somebody lives on and still cross the cabinets
-- serving the area. Left out they drew as "nothing filed" while their own panel listed four
-- operators at 300 — the panel answers from the cabinets, and the map answered only from
-- the doors.
--
-- Cabinet-sized areas only, and the figure five million square metres is shared with
-- api/main.py's CABINET_M2 by hand: two places have to agree about what counts as a claim
-- about a street, and nothing but this comment makes them.
--
-- This is the weaker of the two claims and it is second for that reason: a door says what
-- an operator filed for that door, a cabinet says what it filed for the area around it. A
-- street with doors keeps their answer. A street without them gets the area's, which is
-- the same answer its own panel has been giving all along.
--
-- Same rule as above: mobile is left out, and the open-ended top band stands on its floor.
update street s
set best_mbps = best.mbps
from (
    select s.id, max(coalesce(sb.max_mbps, sb.min_mbps)) as mbps
    from street s
    join coverage_area ca on st_intersects(ca.geom_2d, s.geom::geometry)
    join speed_band sb on sb.id = ca.speed_band_id
    where s.best_mbps is null
      and ca.family <> 'wireless'
      -- The same cut the API makes when it lists who reaches a street, and it has to be
      -- the same or the map paints a claim the panel then refuses to name: half the filed
      -- areas are under four hectares and are about the roads in them, a few hundred are
      -- tens of square kilometres and are about a district. Λίμνης Κορώνειας has no door
      -- on it and crosses nothing but three filings of 36.8 km2 — it was drawn at 100 and
      -- reported as nothing at all, along with 3,188 others.
      and st_area(ca.geom_2d::geography) <= 5000000
    group by s.id
) best
where best.id = s.id
  and s.best_mbps is distinct from best.mbps;
