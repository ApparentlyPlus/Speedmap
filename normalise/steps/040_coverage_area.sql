-- Copper is filed per cabinet polygon, not per point. Reprojected from Greek Grid. The
-- per-service detail comes from the service table because the polygon view is parallel lists.
delete from coverage_area where source = 'register';

insert into coverage_area (
    source, source_ref, provider_id, infra_provider_id, technology, family,
    speed_band_id, normal_band_id, assertion, avail_date, geom, last_seen
)
select distinct on (w.coverid, sp.id, t.code)
    'register', w.coverid, sp.id, ip.id, t.code, t.family,
    w.maxdown, w.nordown, 'declared', w.servstar,
    st_multi(st_transform(g.geom, 4326))::geography, now()
from raw_wiredservice w
join technology t on t.register_id = w.technolo and t.family = 'copper'
join provider sp on sp.register_id = w.servprov
left join provider ip on ip.register_id = w.infrprov
join raw_geo_coverage_copper g on g.coverid = w.coverid
order by w.coverid, sp.id, t.code, w.servstar desc nulls last, w.maxdown desc nulls last
on conflict (source, source_ref, provider_id, technology) do update set
    infra_provider_id = excluded.infra_provider_id,
    family = excluded.family,
    speed_band_id = excluded.speed_band_id,
    normal_band_id = excluded.normal_band_id,
    avail_date = excluded.avail_date,
    geom = excluded.geom,
    last_seen = now();
