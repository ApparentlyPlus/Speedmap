-- Pin each address to the nearest road of its name in its municipality.
--
-- Nearest rather than first. A name can cover several roads, and the register's address
-- carries a position, so the question has an answer to be had. `<->` reads the gist index
-- on street.geom and the candidate set is the handful of components sharing the name, which
-- keeps this a short KNN.
--
-- Addresses whose name matches no road are set to null rather than skipped: a left join,
-- so a road that has since been renamed or removed takes its addresses' pin with it
-- instead of leaving them pointing at a street that no longer answers to that name.
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
        order by s.geom <-> a2.geom
        limit 1
    ) near on true
) found
where found.address_id = a.id
  and a.street_id is distinct from found.street_id;
