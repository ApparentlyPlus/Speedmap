-- What the street panel lists, worked out by the build instead of on every click.
--
-- /streets/{id} assembled its list from three routes at request time, and the third of them
-- sweeps the register's built fiber within reach of the street and then, for every point
-- found, asks which street that point stands nearest. On Ερμού that was 180 ms of a 183 ms
-- answer, plus 13 ms of planning, on a desktop. On the Pi it is most of a second per click,
-- for an answer that only ever changes when the build runs.
--
-- 110 already walks the same three routes to paint the map. It now keeps the row it walked,
-- one per street, operator and technology, and street_provider is read off this table. The
-- panel and the colour cannot disagree, because there is only one derivation left.
create table street_offer (
    street_id bigint not null references street (id) on delete cascade,
    provider_id int not null references provider (id),
    technology text not null references technology (code),
    family text not null,
    -- point for a door on the street, area for a cabinet it runs through, built for fiber
    -- standing beside it that the register never gave an address.
    matched text not null check (matched in ('point', 'area', 'built')),
    avail_date date,
    infra_provider_id int references provider (id),
    speed_band_id int references speed_band (id),
    -- What the line is retailed at, held to its normally available band.
    sold_mbps numeric,
    primary key (street_id, provider_id, technology)
);

-- Where most of a street's own doors say they are, for telling apart two runs of one name.
-- Asked per search result with mode() over every door on the street, per keystroke.
alter table street add locality text;
