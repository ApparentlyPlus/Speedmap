-- A point match is the operator's own filing against this building; an area match says the
-- address falls inside a cabinet's service area. Where both exist, the point wins.
-- Its own rows and no others. Three steps write this table — this one, 070 for the
-- wireless grid and 100 for the builders — and two of them file matched_by 'point', so
-- built_by is what tells them apart. See migration 0047.
delete from address_coverage where built_by = '050';

insert into address_coverage (
    address_id, provider_id, technology, infra_provider_id,
    speed_band_id, normal_band_id, family, matched_by, avail_date, built_by
)
select distinct on (address_id, provider_id, technology)
    address_id, provider_id, technology, infra_provider_id,
    speed_band_id, normal_band_id, family, matched_by, avail_date, '050'
from (
    select ap.address_id, c.provider_id, c.technology, c.infra_provider_id,
           c.speed_band_id, c.normal_band_id, c.family, 'point' as matched_by, c.avail_date
    from address_point ap
    join coverage c on c.source_ref = ap.coverid
    union all
    select a.id, ca.provider_id, ca.technology, ca.infra_provider_id,
           ca.speed_band_id, ca.normal_band_id, ca.family, 'area', ca.avail_date
    from address a
    join coverage_area ca on st_contains(ca.geom_2d, a.geom::geometry)
) matched
order by address_id, provider_id, technology, matched_by, speed_band_id desc nulls last
on conflict (address_id, provider_id, technology) do update set
    built_by = excluded.built_by,
    infra_provider_id = excluded.infra_provider_id,
    speed_band_id = excluded.speed_band_id,
    normal_band_id = excluded.normal_band_id,
    family = excluded.family,
    matched_by = excluded.matched_by,
    avail_date = excluded.avail_date;
