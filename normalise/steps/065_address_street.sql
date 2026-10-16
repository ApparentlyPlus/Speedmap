-- pin each address to the nearest road of its name in its municipality, null if none
update address a
set street_id = found.street_id
from (
    select a2.id as address_id, near.id as street_id
    from address a2
    -- street.sort_key, OSM has ΑΛΕΞΑΝΔΡΟΥ ΠΑΠΑΝΑΣΤΑΣΙΟΥ
    cross join lateral (
        select array_to_string(array(
            select w from unnest(string_to_array(a2.street_fold, ' ')) w order by w collate "C"
        ), ' ') as sort_key
    ) k
    left join lateral (
        select s.id
        from street s
        where s.municipality_id = a2.municipality_id
          and s.sort_key = k.sort_key
        -- id breaks ties between two runs of a name
        order by s.geom <-> a2.geom, s.id
        limit 1
    ) near on true
) found
where found.address_id = a.id
  and a.street_id is distinct from found.street_id;
