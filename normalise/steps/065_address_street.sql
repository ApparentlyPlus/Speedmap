-- pin each address to the nearest road of its name in its municipality, null if none
update address a
set street_id = found.street_id
from (
    select a2.id as address_id, near.id as street_id
    from address a2
    left join lateral (
        select s.id
        from street s
        where s.municipality_id = a2.municipality_id
          and s.name_fold = a2.street_fold
        -- id breaks ties between two runs of a name
        order by s.geom <-> a2.geom, s.id
        limit 1
    ) near on true
) found
where found.address_id = a.id
  and a.street_id is distinct from found.street_id;
