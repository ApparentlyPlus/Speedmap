-- A point match is a filing against this building. An area match means the address falls in a
-- cabinet. built_by tags our rows, since 070 and 100 write here too.
--
-- Compared, not replaced. This used to delete all its rows and insert them again, about ten
-- million rows plus their index entries per build, nearly all identical. On the Pi that write
-- volume was the build. Now the new set is computed once, rows that left it are deleted, and
-- only new or changed rows are written. 070 and 100 do the same. The table ends up exactly
-- as delete-and-insert left it.
with fresh as (
    select distinct on (address_id, provider_id, technology)
        address_id, provider_id, technology, infra_provider_id,
        speed_band_id, normal_band_id, family, matched_by, avail_date
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
    ) src
    -- every column, so ties break the same way every build
    order by address_id, provider_id, technology, matched_by, speed_band_id desc nulls last,
             normal_band_id desc nulls last, infra_provider_id nulls last,
             avail_date nulls last, family
),
gone as (
    delete from address_coverage ac
    where ac.built_by = '050'
      and not exists (
          select 1 from fresh f
          where f.address_id = ac.address_id and f.provider_id = ac.provider_id
            and f.technology = ac.technology
      )
)
insert into address_coverage (
    address_id, provider_id, technology, infra_provider_id,
    speed_band_id, normal_band_id, family, matched_by, avail_date, built_by
)
select address_id, provider_id, technology, infra_provider_id,
       speed_band_id, normal_band_id, family, matched_by, avail_date, '050'
from fresh
on conflict (address_id, provider_id, technology) do update set
    built_by = excluded.built_by,
    infra_provider_id = excluded.infra_provider_id,
    speed_band_id = excluded.speed_band_id,
    normal_band_id = excluded.normal_band_id,
    family = excluded.family,
    matched_by = excluded.matched_by,
    avail_date = excluded.avail_date
where (address_coverage.built_by, address_coverage.infra_provider_id,
       address_coverage.speed_band_id, address_coverage.normal_band_id,
       address_coverage.family, address_coverage.matched_by, address_coverage.avail_date)
      is distinct from
      (excluded.built_by, excluded.infra_provider_id, excluded.speed_band_id,
       excluded.normal_band_id, excluded.family, excluded.matched_by, excluded.avail_date);
