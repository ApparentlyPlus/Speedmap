-- One filed service per row, for the technologies the register locates as points.
-- Copper is filed as cabinet areas instead and goes to coverage_area in 040.
-- The register files (coverid, servprov, technolo) more than once, so distinct on picks
-- the most recent filing rather than letting on conflict touch the same row twice.
-- Cleared first, so the step recomputes rather than fills in. It was insert-on-conflict
-- with no delete, so a filing the operator has since withdrawn stayed here and stayed on
-- the map, with nothing recording that it had gone. See migration 0047.
delete from coverage where source = 'register';

insert into coverage (
    source, source_ref, provider_id, infra_provider_id, technology, family,
    speed_band_id, normal_band_id, assertion, avail_date, geom, last_seen
)
select distinct on (w.coverid, sp.id, t.code)
    'register', w.coverid, sp.id, ip.id, t.code, t.family,
    w.maxdown, w.nordown, 'declared', w.servstar, p.point::geography, now()
from raw_wiredservice w
join provider sp on sp.register_id = w.servprov
join technology t on t.register_id = w.technolo
left join provider ip on ip.register_id = w.infrprov
left join raw_coverpoint p on p.coverid = w.coverid
where t.family <> 'copper'
order by w.coverid, sp.id, t.code, w.servstar desc nulls last, w.maxdown desc nulls last
on conflict (source, source_ref, provider_id, technology) do update set
    infra_provider_id = excluded.infra_provider_id,
    family = excluded.family,
    speed_band_id = excluded.speed_band_id,
    normal_band_id = excluded.normal_band_id,
    avail_date = excluded.avail_date,
    geom = excluded.geom,
    last_seen = now();
