-- Filings with an empty field ("10555,ΑΘΗΝΑ, ,Δ. ΑΘΗΝΑΙΩΝ") can't be matched by name, so
-- link each to the doors within 30 m, at most twenty
with placed as (
    select near.id as address_id, c.coverid
    from raw_coverpoint c
    cross join lateral (
        select a.id
        from address a
        where st_dwithin(a.geom, c.point::geography, 30)
        -- id breaks ties
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
