-- OSM splits a road at every junction: Αχιλλέα Τζελίλη is 8 ways. Streets are the ways
-- grouped by name within a municipality, so a search returns the road once.
-- sort_key is the folded name with its words sorted, which merges ΙΩΑΝΝΗ ΜΕΤΑΞΑ with
-- ΜΕΤΑΞΑ ΙΩΑΝΝΗ. It groups only; searching uses name_fold, which keeps the written order.
create table street (
    id bigserial primary key,
    name text not null,
    name_fold text not null,
    latin_key text not null,
    sort_key text not null,
    municipality_id int references municipality (id),
    highway text not null,
    ways int not null,
    geom geography(MultiLineString, 4326) not null,
    unique nulls not distinct (sort_key, municipality_id)
);

create index on street (name_fold text_pattern_ops);
create index on street using gin (name_fold gin_trgm_ops);
create index on street (latin_key text_pattern_ops);
create index on street using gin (latin_key gin_trgm_ops);
create index on street using gist (geom);
