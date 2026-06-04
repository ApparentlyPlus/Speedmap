-- When an operator was last asked, and whether the asking worked. This is not what the
-- answer was: answers live in availability and are only ever positive there, because a
-- checker that has rotted returns an empty page rather than an error, and writing that
-- down as "no service" would have the site repeat it for a month.
--
-- Two jobs. It is the backoff, so a broken endpoint is retried in hours rather than on
-- every request. And it is the only place adapter rot is visible: without it the symptom
-- is a map that quietly stops improving and nothing that says why.
create table probe_attempt (
    address_id bigint not null references address (id) on delete cascade,
    provider_id int not null references provider (id),
    attempted_at timestamptz not null default now(),
    ok boolean not null,
    serviceable boolean,
    detail text,
    primary key (address_id, provider_id, attempted_at)
);

-- What was asked most recently, which is the only row the read path wants.
create index on probe_attempt (address_id, provider_id, attempted_at desc);

-- How one operator is faring, which is how rot is noticed.
create index on probe_attempt (provider_id, attempted_at desc);
