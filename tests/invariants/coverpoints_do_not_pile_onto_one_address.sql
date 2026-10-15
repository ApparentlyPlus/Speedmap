-- OTE UltraFast once had 50,073 filings on 327 addresses. Builders that file streets sit
-- at 0.8 to 1.3 points per address, 10 is far enough out
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
