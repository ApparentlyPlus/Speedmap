-- a builder in the register and missing from the derived tables (a cross join lateral
-- once dropped FIBERGRID & co., 1.4M doors, with no error)
select p.code, count(distinct ap.address_id) as doors_passed
from provider p
join raw_coverpoint c on c.infrprov = p.register_id and c.prempass > 0
join address_point ap on ap.coverid = c.coverid
where not exists (
    select 1 from address_coverage ac
    where ac.provider_id = coalesce(p.credited_to, p.id)
)
group by p.code;
