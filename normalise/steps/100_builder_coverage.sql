-- Fiber that is in the ground but was never filed as a retail service.
--
-- The register keeps two books, one of filed services and one of built infrastructure. A
-- service filing says "this operator sells a line here". An infrastructure filing says
-- "this operator has built past this door". Vodafone owns no network at all and still files
-- 832,701 services over other people's. Telekom has built past 1.09 million doors and
-- bothers to file 36,012. Read the service book on its own and Telekom lands on 23,041
-- fiber addresses against Vodafone's 601,473, which is a measure of paperwork.
--
-- Two things narrowed this step to almost nothing and both are gone. `p.kind = 'altnet'`
-- excluded the incumbent by category, though Telekom's fiber is fiber on the same terms as
-- anyone else's and Telekom retails seventeen plans over it. The band then came from a
-- `cross join lateral` over `plan`, so a builder with no published tariff produced no rows
-- and left without a word: FIBERGRID (584,662 addresses), UNITEDFIBER (194,830), FIBER2ALL
-- (129,781) and NETFIBER, gone. The join is a left join now and falls back to what the
-- technology itself is retailed at, so an operator who publishes no price list loses the
-- price rather than the network.
delete from address_coverage where built_by = '100';

insert into address_coverage (
    address_id, provider_id, technology, infra_provider_id,
    speed_band_id, family, matched_by, built_by
)
select distinct on (ap.address_id, coalesce(p.credited_to, p.id))
    ap.address_id, coalesce(p.credited_to, p.id), 'FTTH',
    coalesce(p.credited_to, p.id), coalesce(sold.id, fallback.id), 'fiber', 'point', '100'
from address_point ap
join raw_coverpoint c on c.coverid = ap.coverid
join provider p on p.register_id = c.infrprov
-- The band the operator's own fastest plan sits in, where they publish one.
left join lateral (
    select b.id
    from plan pl
    join speed_band b
      on b.min_mbps is not null and b.min_mbps <= pl.down_mbps
    where pl.provider_id = coalesce(p.credited_to, p.id) and pl.down_mbps is not null
    order by b.min_mbps desc
    limit 1
) sold on true
-- What a fiber line is retailed at in this country, for the builders who publish nothing.
left join lateral (
    select b.id
    from technology t
    join speed_band b
      on b.min_mbps is not null and b.min_mbps <= t.sold_mbps
    where t.code = 'FTTH' and t.sold_mbps is not null
    order by b.min_mbps desc
    limit 1
) fallback on true
where c.prempass > 0
  and p.builds_own_network
order by ap.address_id, coalesce(p.credited_to, p.id), coalesce(sold.id, fallback.id) desc
on conflict (address_id, provider_id, technology) do update
  -- coalesce, so this claims only rows nobody else made: 050 keeps its own stamp.
  set speed_band_id = coalesce(address_coverage.speed_band_id, excluded.speed_band_id),
      built_by = coalesce(address_coverage.built_by, excluded.built_by);
