-- The register as fetched, column names and types unchanged. Nothing is
-- interpreted here: re-deriving coverage or address must never need a re-fetch.

-- Resume state per dataset.
create table register_fetch (
    dataset text primary key,
    last_key text,
    fetched integer not null default 0,
    total integer,
    started_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

-- /api/provider.
create table raw_provider (
    id integer primary key,
    name text,
    short_name text
);

-- The code tables, keyed by the endpoint they came from.
create table raw_lookup (
    table_name text not null,
    id integer not null,
    description text,
    long_description text,
    primary key (table_name, id)
);

-- /api/a3b_coverpointftthcoax
-- address is 'postcode,STREET,NUMBER,MUNICIPALITY'; the number is ' ' when absent.
create table raw_coverpoint (
    coverid text primary key,
    infrprov integer,
    method integer,
    infrstar date,
    prempass integer,
    connstat integer,
    intcabl integer,
    vhcn integer,
    address text,
    bngid text,
    point geometry(Point, 4326),
    waitpoin geometry
);

-- /api/a4a_wiredservice
-- maxdown, nordown and maxup are band ids into raw_lookup, not Mbps.
create table raw_wiredservice (
    id integer primary key,
    coverid text,
    servprov integer,
    infrprov integer,
    technolo integer,
    ownrship integer,
    maxdown integer,
    nordown integer,
    maxup integer,
    norup integer,
    servstar date,
    covermod smallint
);

create index on raw_wiredservice (coverid);

-- /api/coverage_ftth
-- The register's own per-point aggregation; the _ids columns are comma separated.
create table raw_coverage_ftth (
    id bigint primary key,
    coverid text,
    servprov_ids text,
    technolo_ids text,
    maxdown_ids text,
    ownrship_ids text,
    servstar_years text,
    servstar_quarters text,
    dimos_id text,
    geom geometry(Point, 4326)
);

create index on raw_coverage_ftth (coverid);

-- /api/coverage_copper
-- Greek Grid, not WGS84. Reprojection is a normalise step.
create table raw_coverage_copper (
    id bigint primary key,
    coverid text,
    servprov_ids text,
    technolo_ids text,
    maxdown_ids text,
    ownrship_ids text,
    servstar_years text,
    servstar_quarters text,
    dimos_id text,
    geom geometry(Geometry, 2100)
);

create index on raw_coverage_copper (coverid);

-- /api/geo_coverage_copper
-- Cabinet service areas, also Greek Grid. No id is served, so coverid is the key.
create table raw_geo_coverage_copper (
    coverid text primary key,
    servprov_ids text,
    technolo_ids text,
    maxdown_ids text,
    ownrship_ids text,
    dimos_id text,
    geom geometry(Geometry, 2100)
);
