-- The scrape's own tables were scaffolding. What they hold belongs with everything else:
-- the plan codes are plans, and how far a street was scanned is a fact about the addresses
-- on it. Only the raw landing table survives, as every other source has one.

-- The highest house number on this street that an operator's checker has been asked about.
-- Null, or a number below this address, means nobody has ever asked and only a live check
-- can answer. It is deliberately not per street: the probe layer asks about an address.
alter table address add checked_to int;

-- A plan is sold over a technology, which is what decides whether its speed is clamped.
alter table plan add technology text references technology (code);

insert into plan (provider_id, external_key, name, family, down_mbps, technology)
select p.id, c.code, c.code,
       case when c.technology = 'FTTH' then 'fibre' else 'copper' end,
       c.down_mbps, c.technology
from cosmote_plan c
cross join (select id from provider where code = 'OTE') p;

drop table cosmote_scan;
drop table cosmote_area;
drop table cosmote_plan;
