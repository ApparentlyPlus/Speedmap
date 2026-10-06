-- Pin each address to the nearest road of its name in its municipality.
--
-- Nearest, since a name can cover several roads and the address has a position. `<->` reads
-- the gist index on street.geom over the few components sharing the name, a short KNN.
--
-- No match sets null (hence the left join), so a renamed or removed road takes its addresses'
-- pins with it.
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
        -- id breaks ties, so a door between two runs of its name lands on the same one each time
        order by s.geom <-> a2.geom, s.id
        limit 1
    ) near on true
) found
where found.address_id = a.id
  and a.street_id is distinct from found.street_id;
