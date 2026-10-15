-- Who reaches each street: doors filed on it, cabinets it crosses, fiber beside it.
-- sold_mbps capped by the normal band, fixed lines only (5G is everywhere)
truncate street_offer, street_provider;

insert into street_offer (
    street_id, provider_id, technology, family, matched, avail_date, infra_provider_id,
    speed_band_id, sold_mbps
)
-- fastest row for each
select distinct on (src.street_id, src.provider_id, src.technology) src.*
from (
    select s.id as street_id, ac.provider_id, ac.technology, ac.family,
           'point' as matched, ac.avail_date, ac.infra_provider_id, ac.speed_band_id,
           least(t.sold_mbps, coalesce(nb.max_mbps, sb.max_mbps)) as sold_mbps
    from street s
    -- 065's pin, by name every component would bleed into the others
    join address a on a.street_id = s.id
    join address_coverage ac on ac.address_id = a.id
    join technology t on t.code = ac.technology
    left join speed_band sb on sb.id = ac.speed_band_id
    left join speed_band nb on nb.id = ac.normal_band_id
    where ac.family <> 'wireless'

    union all

    -- cabinet sized areas only (cabinet_m2, same as the API)
    select s.id, ca.provider_id, ca.technology, ca.family,
           'area', ca.avail_date, ca.infra_provider_id, ca.speed_band_id,
           least(t.sold_mbps, coalesce(nb.max_mbps, sb.max_mbps))
    from street s
    join coverage_area ca on st_intersects(ca.geom_2d, s.geom::geometry)
    join technology t on t.code = ca.technology
    left join speed_band sb on sb.id = ca.speed_band_id
    left join speed_band nb on nb.id = ca.normal_band_id
    where ca.family <> 'wireless'
      and ca.area_m2 <= cabinet_m2()

    union all

    -- 307,300 builder filings with no address, onto the nearest street within built_fiber_m()
    select near.id, coalesce(p.credited_to, p.id), 'FTTH', 'fiber',
           'built', null::date, coalesce(p.credited_to, p.id), null::int, t.sold_mbps
    from raw_coverpoint c
    join provider p on p.register_id = c.infrprov
    join technology t on t.code = 'FTTH'
    cross join lateral (
        select st.id
        from street st
        where st_dwithin(st.geom, c.point::geography, built_fiber_m())
        order by st.geom <-> c.point::geography, st.id
        limit 1
    ) near
    where c.prempass > 0
      and p.builds_own_network
      and c.point is not null
      -- no door on a street, or route one already has it
      and not exists (
          select 1
          from address_point ap
          join address a on a.id = ap.address_id
          where ap.coverid = c.coverid and a.street_id is not null
      )
) src
-- every column, so the panel's pick is stable
order by src.street_id, src.provider_id, src.technology, src.sold_mbps desc nulls last,
         src.matched, src.speed_band_id desc nulls last, src.infra_provider_id nulls last,
         src.avail_date nulls last, src.family;

insert into street_provider (street_id, provider_id, mbps)
select street_id, provider_id, max(sold_mbps)
from street_offer
group by street_id, provider_id;
