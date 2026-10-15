-- Fiber built past a door but never sold there (Telekom: 1.09M doors built, 36,012 filed).
-- Left join on plan, so FIBERGRID & co. with no price list keep their network
with
-- each operator's fastest plan band, once per operator
sold as (
    select distinct on (pl.provider_id) pl.provider_id, b.id
    from plan pl
    join speed_band b
      on b.min_mbps is not null and b.min_mbps <= pl.down_mbps
    where pl.down_mbps is not null
    order by pl.provider_id, b.min_mbps desc
),
-- for builders who publish nothing
fallback as (
    select b.id
    from technology t
    join speed_band b
      on b.min_mbps is not null and b.min_mbps <= t.sold_mbps
    where t.code = 'FTTH' and t.sold_mbps is not null
    order by b.min_mbps desc
    limit 1
),
fresh as (
    select distinct on (ap.address_id, coalesce(p.credited_to, p.id))
        ap.address_id, coalesce(p.credited_to, p.id) as provider_id,
        coalesce(sold.id, (select id from fallback)) as speed_band_id
    from address_point ap
    join raw_coverpoint c on c.coverid = ap.coverid
    join provider p on p.register_id = c.infrprov
    left join sold on sold.provider_id = coalesce(p.credited_to, p.id)
    where c.prempass > 0
      and p.builds_own_network
    order by ap.address_id, coalesce(p.credited_to, p.id),
             coalesce(sold.id, (select id from fallback)) desc
),
gone as (
    delete from address_coverage ac
    where ac.built_by = '100'
      and not exists (
          select 1 from fresh f
          where f.address_id = ac.address_id and f.provider_id = ac.provider_id
            and ac.technology = 'FTTH'
      )
)
insert into address_coverage (
    address_id, provider_id, technology, infra_provider_id,
    speed_band_id, family, matched_by, built_by
)
select address_id, provider_id, 'FTTH', provider_id, speed_band_id, 'fiber', 'point', '100'
from fresh
on conflict (address_id, provider_id, technology) do update
  -- only claims rows nobody else made, 050 keeps its stamp
  set speed_band_id = case
          when address_coverage.built_by = '100' then excluded.speed_band_id
          else coalesce(address_coverage.speed_band_id, excluded.speed_band_id)
      end,
      built_by = coalesce(address_coverage.built_by, excluded.built_by)
  where (address_coverage.speed_band_id, address_coverage.built_by)
        is distinct from (
            case
                when address_coverage.built_by = '100' then excluded.speed_band_id
                else coalesce(address_coverage.speed_band_id, excluded.speed_band_id)
            end,
            coalesce(address_coverage.built_by, excluded.built_by)
        );
