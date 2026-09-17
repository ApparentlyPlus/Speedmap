-- How large a filed area may be and still say anything about one street, in one place.
--
-- Half the areas in the register are under four hectares — a cabinet and the streets around
-- it, which is a claim about those streets. A few hundred are tens of square kilometres and
-- one is 1,522: those are exchange regions, and a street inside one has been told only that
-- the operator serves somewhere in the district. Intersecting them street by street turns
-- "Nova is in this part of Greece" into "Nova reaches this road", which is not what was
-- filed and is how an operator came to appear on almost every street in a region.
--
-- Five square kilometres keeps 97% of the areas and drops the ones that are not about
-- streets. It is a blunt cut, and the register gives nothing better to cut on: every row of
-- it, cabinet and region alike, is filed as source `register`, assertion `declared`.
--
-- The figure used to live in api/main.py and again in 110_street_speed.sql, copied by hand,
-- with a comment in each asking the next reader to keep them equal. Two places that have to
-- agree and nothing making them is the same shape as the tile field names, and it is fixed
-- the same way: one definition, and everybody asks it.
create function cabinet_m2() returns double precision
    language sql immutable parallel safe
    return 5000000::double precision;

comment on function cabinet_m2() is
    'The largest filed area that still names a street, in square metres.';

-- Stored, because every consumer filters on it and st_area over a geography is not cheap:
-- the street panel computed it for every cabinet a street crosses, on every click.
--
-- Cast to geography, because geom_2d is geometry(4326) and st_area on that is square
-- DEGREES. A cap written without the cast is always true and silently does nothing.
alter table coverage_area add area_m2 double precision
    generated always as (st_area(geom::geography)) stored;

-- The cabinets, which is what every street-level question wants and is 97% of the table.
-- Paired with the existing gist on geom_2d: the planner intersects first and cuts second.
create index coverage_area_cabinet_idx on coverage_area using gist (geom_2d)
    where area_m2 <= 5000000;
