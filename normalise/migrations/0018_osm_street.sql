-- Streets from OpenStreetMap, verbatim. The register only names streets where fibre or coax
-- was filed, which is 165 of 333 municipalities: Lagkadas has 207 copper cabinets and no
-- addresses at all. OSM names those streets, so search can answer where the register cannot.
create table raw_osm_street (
    osm_id bigint primary key,
    name text not null,
    highway text not null,
    geom geometry(LineString, 4326) not null
);

create index on raw_osm_street using gist (geom);
