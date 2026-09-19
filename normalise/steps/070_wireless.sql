-- The grid is a regular 100 m lattice in Greek Grid, so an address finds its cell by
-- arithmetic rather than containment. tech flag 2 means planned, so test for 1, not truthy.
delete from address_coverage where built_by = '070';

with cell as (
    select a.id, floor(st_x(p.g) / 100)::int || '|' || floor(st_y(p.g) / 100)::int as gridid
    from address a
    cross join lateral (select st_transform(a.geom::geometry, 2100) as g) p
)
insert into address_coverage (
    address_id, provider_id, technology, infra_provider_id,
    speed_band_id, family, matched_by, built_by
)
select distinct on (c.id, sp.id)
    c.id, sp.id,
    case when g.tech5gf = 1 then 'FWA_5G' else 'FWA_4G' end,
    ip.id, nullif(g.maxdown, 0), 'wireless', 'cell', '070'
from cell c
join raw_wireless_grid g on g.gridid = c.gridid
join provider sp on sp.register_id = g.servprov
left join provider ip on ip.register_id = g.infrprov
where g.tech4gf = 1 or g.tech5gf = 1
order by c.id, sp.id, g.tech5gf desc, g.maxdown desc nulls last
on conflict (address_id, provider_id, technology) do update set
    built_by = excluded.built_by,
    infra_provider_id = excluded.infra_provider_id,
    speed_band_id = excluded.speed_band_id,
    family = excluded.family,
    matched_by = excluded.matched_by;
