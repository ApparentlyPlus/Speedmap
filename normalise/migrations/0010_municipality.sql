-- /api/dimos, the 333 Kallikratis municipalities.
create table raw_dimos (
    gid int primary key,
    kalcode4 text,
    d1 text,
    shape_area double precision,
    shape_len double precision,
    geom geometry(MultiPolygon, 2100),
    geom4326 geometry(MultiPolygon, 4326)
);

create table municipality (
    id int primary key,
    kallikratis_code text,
    name text not null,
    geom geography(MultiPolygon, 4326) not null
);

create index on municipality using gist (geom);

-- The register's fourth address field is the locality, not the municipality:
-- ΣΤΑΥΡΟΥΠΟΛΗ is in ΔΗΜΟΣ ΠΑΥΛΟΥ ΜΕΛΑ, ΣΥΚΙΕΣ in ΔΗΜΟΣ ΝΕΑΠΟΛΗΣ - ΣΥΚΕΩΝ. It is also
-- written inconsistently, ΘΕΣΣΑΛΟΝΙΚΗ 31,062 times against Δ. ΘΕΣΣΑΛΟΝΙΚΗΣ 28,764.
-- The text stays as filed; the municipality is resolved from the point instead.
alter table address rename column municipality to locality;
alter table address add municipality_id int references municipality (id);

alter table address drop constraint address_postcode_street_street_no_municipality_key;
alter table address add constraint address_key
    unique nulls not distinct (postcode, street, street_no, municipality_id);
