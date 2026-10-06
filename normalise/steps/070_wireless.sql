-- The grid is a regular 100 m lattice in Greek Grid, so an address finds its cell by
-- arithmetic. A tech flag of 2 means planned, so test for 1 and not for truthy.
-- Compared, not replaced, like 050.
with cell as (
    select a.id, floor(st_x(p.g) / 100)::int || '|' || floor(st_y(p.g) / 100)::int as gridid
    from address a
    cross join lateral (select st_transform(a.geom::geometry, 2100) as g) p
),
-- One row per generation filed. Keyed on the operator alone, 5G won and 4G was dropped wherever
-- both reached, so 4G home plans never qualified where 5G did: 15 FWA_4G rows nationally
-- against 1.8 million FWA_5G.
fresh as (
    select distinct on (c.id, coalesce(sp.credited_to, sp.id), gen.technology)
        c.id as address_id, coalesce(sp.credited_to, sp.id) as provider_id,
        gen.technology, coalesce(ip.credited_to, ip.id) as infra_provider_id,
        gen.band as speed_band_id, 'wireless' as family, 'cell' as matched_by,
        '070' as built_by
    from cell c
    join raw_wireless_grid g on g.gridid = c.gridid
    join provider sp on sp.register_id = g.servprov
    left join provider ip on ip.register_id = g.infrprov
    -- one band per cell and it's 5G's, so 4G gets none where both are flagged
    cross join lateral (
        select 'FWA_5G' as technology, nullif(g.maxdown, 0) as band where g.tech5gf = 1
        union all
        select 'FWA_4G', case when g.tech5gf = 1 then null else nullif(g.maxdown, 0) end
        where g.tech4gf = 1
    ) gen
    -- the grid row's id last, so ties break the same way every build
    order by c.id, coalesce(sp.credited_to, sp.id), gen.technology, g.maxdown desc nulls last,
             g.id
),
gone as (
    delete from address_coverage ac
    where ac.built_by = '070'
      and not exists (
          select 1 from fresh f
          where f.address_id = ac.address_id and f.provider_id = ac.provider_id
            and f.technology = ac.technology
      )
)
insert into address_coverage (
    address_id, provider_id, technology, infra_provider_id,
    speed_band_id, family, matched_by, built_by
)
select address_id, provider_id, technology, infra_provider_id,
       speed_band_id, family, matched_by, built_by
from fresh
on conflict (address_id, provider_id, technology) do update set
    built_by = excluded.built_by,
    infra_provider_id = excluded.infra_provider_id,
    speed_band_id = excluded.speed_band_id,
    family = excluded.family,
    matched_by = excluded.matched_by
where (address_coverage.built_by, address_coverage.infra_provider_id,
       address_coverage.speed_band_id, address_coverage.family, address_coverage.matched_by)
      is distinct from
      (excluded.built_by, excluded.infra_provider_id, excluded.speed_band_id,
       excluded.family, excluded.matched_by);
