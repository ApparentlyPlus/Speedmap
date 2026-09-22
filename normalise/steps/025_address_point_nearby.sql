-- Filings that name a postcode and no street, placed by where they actually are.
--
-- 020 links a coverpoint to an address by parsing the address the operator filed with it
-- and matching street, number, postcode and municipality. That works on a filing like
-- "10674,ΛΕΩΦΟΡΟΣ ΒΑΣΙΛΙΣΣΗΣ ΣΟΦΙΑΣ,23,Δ. ΑΘΗΝΑΙΩΝ" and falls apart on
-- "10555,ΑΘΗΝΑ, ,Δ. ΑΘΗΝΑΙΩΝ", which names a city in the street field and leaves the
-- number blank. Every such filing in a postcode matches the same row, so they stack:
-- 343,930 of Telekom's points and all 50,064 of OTE UltraFast's, 991,000 premises between
-- them and the builders, landing on a few hundred addresses. OTE UltraFast reached 327.
--
-- The map showed the result as copper through central Athens, Salamina, Rhodes and Chania,
-- which is where the fiber is densest and where people look first.
--
-- These points carry coordinates, and coordinates are the one thing the filing gets right.
-- The stacked links are dropped and replaced by the addresses nearest the point.
delete from address_point ap
using raw_coverpoint c
where ap.coverid = c.coverid
  and c.address ~ ',[[:space:]]*,';

-- 30 m, and at most twenty doors.
--
-- A filing is a distribution point passing a handful of premises, not a district. Half of
-- these sit within 30 m of two addresses or fewer and 95% within 30 m of fifteen, so the
-- cap bites only where the address index has piled a block into one spot: one point had
-- 956 doors inside the radius and crediting a network to all of them is a guess wearing a
-- number. Points with nothing inside 30 m stay unplaced, which is most of the rural ones.
insert into address_point (address_id, coverid)
select near.id, c.coverid
from raw_coverpoint c
cross join lateral (
    select a.id
    from address a
    where st_dwithin(a.geom, c.point::geography, 30)
    order by a.geom <-> c.point::geography
    limit 20
) near
where c.address ~ ',[[:space:]]*,'
  and c.point is not null
on conflict do nothing;
