-- A network in the register and nowhere in the derived tables.
--
-- Nothing caught this when it happened. 100_builder_coverage took its band from a `cross join
-- lateral` over `plan`, which yields no row when nothing matches, so FIBERGRID, UNITEDFIBER,
-- FIBER2ALL and NETFIBER fell out of the build: 1.4 million doors between them. No error, no
-- odd count. Every other invariant kept passing, since each asks whether what's there is
-- right. Whether something is missing is another question.
--
-- An operator that built past a door the register can place reaches that door. Speed and
-- terms are checked elsewhere.
select p.code, count(distinct ap.address_id) as doors_passed
from provider p
join raw_coverpoint c on c.infrprov = p.register_id and c.prempass > 0
join address_point ap on ap.coverid = c.coverid
where not exists (
    select 1 from address_coverage ac
    where ac.provider_id = coalesce(p.credited_to, p.id)
)
group by p.code;
