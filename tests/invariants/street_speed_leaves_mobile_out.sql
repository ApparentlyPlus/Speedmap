-- A street painted by a signal that reaches every street.
--
-- 5G covers nearly every address with a 300-1000 band, so counting it put 40,775 of the 40,796
-- streets with a figure at exactly 1000. One number, one colour, a map that said nothing. A
-- street is about the line that runs down it. This catches it because the symptom is a map
-- that looks fine.
--
-- It asks "has a figure but no fixed line it could have come from" instead of recomputing the
-- figure. The older version compared against doors only and knew nothing of cabinets, so once
-- doorless streets (half of them) could take a figure from the area around them it flagged
-- correct streets: 80 at first, 1,138 once 110 and 120 became one derivation. An invariant
-- that cries wolf is worse than none, because the next person turns it off.
--
-- It cried wolf again (394 streets) when 110 gained a route this didn't know. Every route 110
-- reads has to be one this reads, in the same order:
--
--   * doors pinned to the street through street_id. 065 decides which run of a name a door
--     is on, and asking by name would let a door 2 km away vouch for the figure.
--   * cabinets it runs through, cut at cabinet_m2().
--   * built fiber within built_fiber_m() of it, which is how a village with fifty indexed
--     doors reaches a gigabit. (This one is broader than 110's, which only credits the
--     nearest street, so it can't flag a street 110 rightly painted.)
--
-- A street with a speed and none of the three wears a number nothing fixed ever gave it.
select s.id, s.name, s.best_mbps
from street s
where s.best_mbps is not null
  and not exists (
      select 1
      from address a
      join address_coverage ac on ac.address_id = a.id
      where a.street_id = s.id
        and ac.family <> 'wireless'
  )
  and not exists (
      select 1
      from coverage_area ca
      where ca.family <> 'wireless'
        and ca.area_m2 <= cabinet_m2()
        and st_intersects(ca.geom_2d, s.geom::geometry)
  )
  and not exists (
      select 1
      from raw_coverpoint c
      join provider p on p.register_id = c.infrprov
      where c.prempass > 0
        and p.builds_own_network
        and st_dwithin(s.geom, c.point::geography, built_fiber_m())
  );
