-- Filings with an empty field, placed by where they are.
--
-- 020 links a coverpoint to an address by parsing what the operator filed and matching street,
-- number, postcode and municipality. Fine for "10674,ΛΕΩΦΟΡΟΣ ΒΑΣΙΛΙΣΣΗΣ ΣΟΦΙΑΣ,23,Δ. ΑΘΗΝΑΙΩΝ".
-- Useless for "10555,ΑΘΗΝΑ, ,Δ. ΑΘΗΝΑΙΩΝ", a city in the street field and no number: every
-- such filing in a postcode matches the same row. They stacked up, 343,930 of Telekom's points
-- and all 50,064 of OTE UltraFast's (991,000 premises with the builders' ones) on a few hundred
-- addresses, and the map showed copper through central Athens, Salamina, Rhodes and Chania,
-- where fiber is densest and people look first.
--
-- The coordinates are the one thing these filings get right, so each is linked to the doors
-- nearest it. 020 skips them, and the placed links are compared, never deleted and remade:
-- over an unchanged register a rebuild writes none of the 1.9 million.
--
-- 30 m and at most twenty doors. A filing is a distribution point passing a handful of
-- premises. Half sit within 30 m of two addresses or fewer and 95% within 30 m of fifteen, so
-- the cap only bites where the index piled a block into one spot (one point had 956 doors in
-- range). Points with nothing inside 30 m stay unplaced, most of them rural.
with placed as (
    select near.id as address_id, c.coverid
    from raw_coverpoint c
    cross join lateral (
        select a.id
        from address a
        where st_dwithin(a.geom, c.point::geography, 30)
        -- the id breaks ties at equal distance, or which twenty got linked changed every build
        order by a.geom <-> c.point::geography, a.id
        limit 20
    ) near
    where c.address ~ ',[[:space:]]*,'
      and c.point is not null
),
gone as (
    delete from address_point ap
    using raw_coverpoint c
    where ap.coverid = c.coverid
      and c.address ~ ',[[:space:]]*,'
      and not exists (
          select 1 from placed p
          where p.address_id = ap.address_id and p.coverid = ap.coverid
      )
)
insert into address_point (address_id, coverid)
select address_id, coverid from placed
on conflict do nothing;
