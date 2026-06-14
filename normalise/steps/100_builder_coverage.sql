-- A builder that sells to households covers the premises it passes, and the register never
-- records that: their fibre is filed as infrastructure under infrprov, and their retail arm
-- files no service at all. So one of them passes 112,739 addresses and could be offered at
-- none of them, while we hold their tariff.
-- Who this applies to is taken from the data rather than named: an operator that builds its
-- own network, sells a tariff we hold, and is neither the incumbent nor a mobile network.
-- The wholesale builders fall out because nobody can buy from them, which is the same test
-- a person applies.
insert into address_coverage (
    address_id, provider_id, technology, infra_provider_id, family, matched_by
)
select distinct ap.address_id, p.id, 'FTTH', p.id, 'fibre', 'point'
from address_point ap
join raw_coverpoint c on c.coverid = ap.coverid
join provider p on p.register_id = c.infrprov
where c.prempass > 0
  and p.builds_own_network
  and p.kind = 'altnet'
  and exists (select 1 from plan pl where pl.provider_id = p.id)
on conflict (address_id, provider_id, technology) do nothing;
