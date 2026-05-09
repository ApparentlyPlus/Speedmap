-- The operator's own availability checker, asked once per street number and kept. Their
-- hierarchy is not Καλλικράτης: nomos, dimos and area are their spellings, and matching
-- them to a municipality is the job of the build step, not of this table.
-- Timestamps arrive naive from the scrape and are Athens local time.
create table raw_cosmote (
    id bigint primary key,
    nomos text not null,
    dimos text not null,
    area text,
    street text not null,
    street_no int not null,
    plans text not null,
    observed_at timestamp not null,
    geom geography(Point, 4326),
    geocode_precision text,
    kaek text
);

create index on raw_cosmote (dimos, area);
create index on raw_cosmote using gist (geom);

-- What the operator sells, keyed by the code their checker returns. Technology is left
-- for the build step: a 100 Mbps offer is vectored copper in one street and fibre in the
-- next, and only the register knows which is under this address.
create table cosmote_plan (
    code text primary key,
    down_mbps numeric not null
);

insert into cosmote_plan (code, down_mbps) values
    ('ADSL_24M', 24),
    ('FBR_50M', 50),
    ('FBR_100M', 100),
    ('FBR_200M', 200),
    ('FBR_300M', 300),
    ('FBR_500M', 500),
    ('FBR_1G', 1000),
    ('FBR_3G', 3000);
