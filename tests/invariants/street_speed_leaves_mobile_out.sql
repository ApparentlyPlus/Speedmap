-- A figure with no fixed line behind it. 5G put 40,775 of 40,796 streets at 1000.
-- Must read every route 110 does (pinned doors, cabinets under cabinet_m2(), built fiber
-- within built_fiber_m()) or it flags streets 110 painted correctly
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
