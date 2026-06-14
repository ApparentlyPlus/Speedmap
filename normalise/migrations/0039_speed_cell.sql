-- What people actually measured, tile by tile, from Ookla's quarterly open data. Everything
-- else here is what an operator says: this is the only source that disagrees with them.
--
-- The tiles are a regular grid at zoom 16, roughly 600 m across, so an address finds its
-- own by arithmetic on its coordinates rather than by a spatial join, exactly as it finds
-- its wireless cell. The geometry is kept for drawing, not for looking up.
--
-- Fixed and mobile are Ookla's own words and are kept as such: their fixed is every kind of
-- landline together, which maps onto no single technology of ours.
create table speed_cell (
    quadkey text not null,
    family text not null check (family in ('fixed', 'mobile')),
    observed_on date not null,
    avg_down_mbps numeric not null,
    avg_up_mbps numeric not null,
    latency_ms int,
    tests int not null,
    devices int not null,
    geom geography(Point, 4326) not null,
    primary key (quadkey, family, observed_on)
);

-- The read path asks for one tile and wants the most recent quarter of it.
create index on speed_cell (quadkey, family, observed_on desc);

create index on speed_cell using gist (geom);
