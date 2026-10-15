-- OTE, OTE UltraFast and the two rural concessions are all Telekom. Every step resolves
-- credited_to, an alias here means one forgot
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
