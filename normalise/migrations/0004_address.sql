-- The national address index. search_key is accent-folded and uppercased at ingest.
create table address (
    id bigserial primary key,
    postcode text,
    street text not null,
    street_no text,
    municipality text,
    region text,
    geom geography(Point, 4326) not null,
    premises int,
    connected boolean,
    vhcn boolean,
    search_key text not null,
    -- nulls not distinct, or two rows with no postcode never collide and the index fills with
    -- duplicates.
    unique nulls not distinct (postcode, street, street_no, municipality)
);

create index on address using gin (search_key gin_trgm_ops);
create index on address using gist (geom);
