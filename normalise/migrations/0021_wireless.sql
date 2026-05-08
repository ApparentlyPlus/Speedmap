-- /api/wireless1000, the 1km grid with geometry. 133,723 cells over Greece.
create table raw_wireless_cell (
    uniqueid text primary key,
    servprov_ids text,
    maxdown_ids text,
    dimos_id text,
    geom geometry(Polygon, 2100)
);

create index on raw_wireless_cell using gist (geom);

-- /api/a4b_wirelessservicegrid, filtered to fixed wireless. The full grid is 53.3M rows
-- and includes mobile-only cells: 6932|46182 has tech4gm but neither fixed flag, and the
-- 1km aggregate lists four providers there. Only the fixed flags can replace a landline.
create table raw_wireless_grid (
    id bigint primary key,
    gridid text not null,
    servprov integer,
    infrprov integer,
    tech3g integer,
    tech4gm integer,
    tech5gm integer,
    tech4gf integer,
    tech5gf integer,
    techoth integer,
    foretech date,
    maxdown integer,
    maxup integer,
    vhcn integer
);

create index on raw_wireless_grid (gridid);
