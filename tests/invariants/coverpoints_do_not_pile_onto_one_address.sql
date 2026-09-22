-- A builder whose infrastructure collapses onto a handful of addresses.
--
-- every_builder_reaches_somewhere asks whether an operator reaches anything at all, and
-- that turned out to be far too little to ask. OTE UltraFast passed it while its 50,073
-- filings landed on 327 addresses, 153 points stacked on every one of them, because the
-- register files a third of Telekom's network with a postcode and no street and
-- address_point joins on the street. The coverage was counted. It was in the wrong places,
-- or rather in one place, and every total looked healthy.
--
-- A filing describes a distribution point passing a few premises, so points and addresses
-- run close to parallel: every builder who files a street sits between 0.8 and 1.3. Ten is
-- nowhere near that and needs no argument about where the true line falls.
select p.code,
       count(distinct c.coverid) as points,
       count(distinct ap.address_id) as addresses,
       round(count(distinct c.coverid)::numeric
             / nullif(count(distinct ap.address_id), 0), 1) as points_per_address
from raw_coverpoint c
join provider p on p.register_id = c.infrprov
join address_point ap on ap.coverid = c.coverid
where c.prempass > 0
group by p.code
having count(distinct c.coverid) > 1000
   and count(distinct c.coverid)::numeric
       / nullif(count(distinct ap.address_id), 0) > 10;
