-- A network that exists in the register and nowhere in the derived tables.
--
-- Nothing here covered this when it mattered. 100_builder_coverage took its speed band from
-- a `cross join lateral` over `plan`, and a cross join that matches nothing produces no row
-- at all, so FIBERGRID, UNITEDFIBER, FIBER2ALL and NETFIBER fell out of the build. Between
-- them they pass 1.4 million doors. No error was raised and no count looked wrong. The
-- other invariants all went on passing, because each of them asks whether what is there is
-- right, which is a different question from whether anything is missing.
--
-- An operator who has built past a door the register can place reaches that door. Speed
-- and terms are checked elsewhere.
select p.code, count(distinct ap.address_id) as doors_passed
from provider p
join raw_coverpoint c on c.infrprov = p.register_id and c.prempass > 0
join address_point ap on ap.coverid = c.coverid
where not exists (
    select 1 from address_coverage ac
    where ac.provider_id = coalesce(p.credited_to, p.id)
)
group by p.code;
