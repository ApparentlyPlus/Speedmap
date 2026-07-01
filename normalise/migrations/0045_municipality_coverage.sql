-- What a municipality looks like from far enough away to see all of it.
--
-- The map draws streets, and a street is invisible at the zoom where the country fits on
-- the screen. So the first thing anyone sees is nothing at all: no basemap, no coastline,
-- no landmass — a black rectangle and a panel telling them to zoom in, somewhere, with no
-- clue where. A map has to be a map at every zoom it can be at.
--
-- Fibre rather than the fastest anything, because the fastest anything is 5G and 5G reaches
-- nearly every address in the country: a map of it is a map of Greece, coloured in one
-- colour. Fibre is the thing that varies — 124 municipalities have none at all and 77 have
-- it almost everywhere — and it is what people mean when they ask who has good internet.
create table municipality_coverage (
    municipality_id integer primary key references municipality (id) on delete cascade,
    addresses integer not null,
    fibre integer not null,
    best_mbps numeric
);
