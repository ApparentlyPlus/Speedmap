-- One row per (source, place, provider, technology), never overwritten.
create table coverage (
    id bigserial primary key,
    source text not null references source (name),
    source_ref text not null,
    provider_id int not null references provider (id),
    technology text not null references technology (code),
    family text not null,
    max_down_mbps numeric,
    assertion assertion not null,
    avail_date date,
    geom geography(Point, 4326),
    first_seen timestamptz not null default now(),
    last_seen timestamptz not null default now(),
    unique (source, source_ref, provider_id, technology)
);

create index on coverage using gist (geom);

-- Copper is filed as cabinet service areas, not points. Written out rather than
-- created with LIKE, which copies neither the foreign keys nor a sequence of its own.
create table coverage_area (
    id bigserial primary key,
    source text not null references source (name),
    source_ref text not null,
    provider_id int not null references provider (id),
    technology text not null references technology (code),
    family text not null,
    max_down_mbps numeric,
    assertion assertion not null,
    avail_date date,
    geom geography(MultiPolygon, 4326),
    first_seen timestamptz not null default now(),
    last_seen timestamptz not null default now(),
    unique (source, source_ref, provider_id, technology)
);

create index on coverage_area using gist (geom);
