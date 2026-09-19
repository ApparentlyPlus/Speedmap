-- Builders file their fibre as infrastructure and sell no service, so the register shows
-- them passing premises they could never be bought at. Band comes from their fastest plan.
delete from address_coverage where built_by = '100';

insert into address_coverage (
    address_id, provider_id, technology, infra_provider_id,
    speed_band_id, family, matched_by, built_by
)
select distinct ap.address_id, p.id, 'FTTH', p.id, band.id, 'fibre', 'point', '100'
from address_point ap
join raw_coverpoint c on c.coverid = ap.coverid
join provider p on p.register_id = c.infrprov
cross join lateral (
    select b.id
    from plan pl
    join speed_band b
      on b.min_mbps is not null and b.min_mbps <= pl.down_mbps
    where pl.provider_id = p.id and pl.down_mbps is not null
    order by b.min_mbps desc
    limit 1
) band
where c.prempass > 0
  and p.builds_own_network
  and p.kind = 'altnet'
on conflict (address_id, provider_id, technology) do update
  -- coalesce, so this claims only rows nobody else made: 050 keeps its own stamp.
  set speed_band_id = coalesce(address_coverage.speed_band_id, excluded.speed_band_id),
      built_by = coalesce(address_coverage.built_by, excluded.built_by);
