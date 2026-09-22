-- The register files one company under four names. A derived table holds one.
--
-- OTE, OTE UltraFast and the two rural concessions are all Telekom to anybody buying a
-- line. The alias rows stay in `provider` because `register_id` is how raw_* is joined, and
-- every step that writes a derived table resolves through `credited_to` before storing an
-- id. A provider with a `credited_to` appearing in a derived table means one of those steps
-- was written without it, and the symptom is a company's coverage quietly split in four.
select 'address_coverage' as source, p.code, count(*) as rows
from address_coverage ac
join provider p on p.id in (ac.provider_id, ac.infra_provider_id)
where p.credited_to is not null
group by p.code

union all

select 'street_provider', p.code, count(*)
from street_provider sp
join provider p on p.id = sp.provider_id
where p.credited_to is not null
group by p.code

union all

select 'coverage', p.code, count(*)
from coverage c
join provider p on p.id in (c.provider_id, c.infra_provider_id)
where p.credited_to is not null
group by p.code

union all

select 'coverage_area', p.code, count(*)
from coverage_area ca
join provider p on p.id in (ca.provider_id, ca.infra_provider_id)
where p.credited_to is not null
group by p.code;
