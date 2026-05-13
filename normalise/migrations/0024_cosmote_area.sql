-- The operator's dimoi are not Καλλικράτης and their names do not resolve: street names
-- repeat nationwide, so a vote over names maps almost nothing. Their coordinates do
-- resolve, and one (dimos, area) pair sits in one municipality, so the pair is learned
-- once from the rows the scrape geocoded confidently and then applied to the rest.
-- area is empty rather than null, so the pair can be a primary key.
create table cosmote_area (
    dimos text not null,
    area text not null,
    municipality_id int not null references municipality (id),
    placed int not null,
    primary key (dimos, area)
);

-- Speed implies the medium, because vectored copper stops short of 200 Mbps. A hundred is
-- the one ambiguous rung: it is fibre on a fibre street and vectored copper elsewhere, and
-- since the technology is taken from the best plan at the address, a street with fibre
-- has already resolved it at a higher rung.
alter table cosmote_plan add technology text references technology (code);

update cosmote_plan set technology = case
    when down_mbps >= 200 then 'FTTH'
    when down_mbps >= 100 then 'VECT_VDSL'
    when down_mbps >= 50 then 'VDSL'
    else 'ADSL'
end;

alter table cosmote_plan alter column technology set not null;
