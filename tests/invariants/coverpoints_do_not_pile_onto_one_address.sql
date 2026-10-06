-- A builder whose infrastructure collapses onto a handful of addresses.
--
-- every_builder_reaches_somewhere only asks whether an operator reaches anything, which turned
-- out to be far too little. OTE UltraFast passed it with 50,073 filings on 327 addresses, 153
-- points stacked on each. The register files a third of Telekom's network with a postcode and
-- no street, and address_point joined on the street. Everything was counted, all of it in one
-- place, and every total looked healthy.
--
-- A filing is a distribution point passing a few premises, so points and addresses run nearly
-- one to one: every builder that files streets sits between 0.8 and 1.3. Ten is far enough
-- out that nobody needs to argue where the real line is.
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
