-- A street painted by a signal that reaches every street.
--
-- 5G covers nearly every address in the country and files a 300-1000 band wherever it does,
-- so counting it made 40,775 of the 40,796 streets that had a figure at all come out at
-- exactly 1000: one number, one colour, and a map that told the reader nothing. What a
-- street is asking about is the line that runs down it.
--
-- Caught here rather than by eye, because the symptom is a map that looks fine.
--
-- Asked as "has a figure but no fixed line to have got it from" rather than by recomputing
-- the figure and comparing. The older form compared against the doors alone and knew
-- nothing of the cabinets a street crosses, so once a street with no door on it could take
-- its figure from the area around it, which is half of them, the query started reporting
-- streets that were perfectly correct: 80 of them at first, and 1,138 once the two
-- derivations in 110 and 120 were made one. An invariant that cries wolf is worse than none,
-- because the next person to read it turns it off.
--
-- It cried wolf a third time, 394 streets' worth, when 110 gained a route it did not know
-- about. Every route 110 reads has to be a route this reads, so the list below is the same
-- list, in the same order:
--
--   * the doors pinned to the street, through street_id rather than the folded name. 065
--     decides which run of a name a door belongs to, and asking by name again would let a
--     door two kilometres away vouch for a figure it had nothing to do with.
--   * the cabinets it runs through, cut at cabinet_m2().
--   * the built fiber standing within built_fiber_m() of it. That is how a village reaches
--     a gigabit when the address index holds fifty doors for the whole municipality.
--
-- A street with a speed and none of the three is wearing a number nothing fixed ever gave it.
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
