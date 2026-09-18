-- A builder that sells to households covers the premises it passes, and the register never
-- records that: their fibre is filed as infrastructure under infrprov, and their retail arm
-- files no service at all. So one of them passes 112,739 addresses and could be offered at
-- none of them, while we hold their tariff.
-- Who this applies to is taken from the data rather than named: an operator that builds its
-- own network, sells a tariff we hold, and is neither the incumbent nor a mobile network.
-- The wholesale builders fall out because nobody can buy from them, which is the same test
-- a person applies.
--
-- They file no service, so they file no speed either, and a null band read as "reaches this
-- street, files nothing" — which painted every street of theirs as unknown on a map whose
-- whole subject is speed. These are fibre networks and every plan on them is fibre, so the
-- band is taken from the fastest plan they actually sell: asserted from the tariff we hold
-- rather than assumed to be a gigabit because altnets usually are.
-- Its own rows and no others. This step refines 050's rows as well as adding its own —
-- the conflict clause below fills a band 050 left null — and an updated row keeps 050's
-- stamp, so clearing '100' takes back exactly the addresses this step invented and leaves
-- the register's alone. See migration 0047.
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
  set speed_band_id = coalesce(address_coverage.speed_band_id, excluded.speed_band_id),
      -- Claim the row only if nobody else has. This step both invents addresses and refines
      -- 050's, and the two need telling apart at the next rebuild: a row 050 filed keeps
      -- 050's stamp and is cleared by 050, a row this step invented carries this one and is
      -- cleared here. Without the coalesce it stole every row it touched, and 050 would
      -- stop clearing its own work; without setting it at all — which is how it was first
      -- written — the rows this step invents are stamped by nobody and never cleared by
      -- anybody, which is the staleness migration 0047 exists to end.
      built_by = coalesce(address_coverage.built_by, excluded.built_by);
