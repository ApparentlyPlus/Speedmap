-- The answer cache. A failed probe is never written here as not serviceable:
-- only an explicit upstream denial is.
create table availability (
    address_id bigint not null references address (id),
    provider_id int not null references provider (id),
    technology text not null references technology (code),
    max_down_mbps numeric,
    serviceable boolean not null,
    source text not null check (source in ('register', 'isp-live', 'inferred-street')),
    assertion assertion not null,
    observed_at timestamptz not null,
    expires_at timestamptz not null,
    raw jsonb,
    primary key (address_id, provider_id, technology)
);

create index on availability (expires_at) where serviceable;
