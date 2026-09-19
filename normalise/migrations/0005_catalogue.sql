create table plan (
    id serial primary key,
    provider_id int not null references provider (id),
    external_key text not null,
    name text not null,
    family text not null check (family in ('fibre', 'copper', 'mobile', 'satellite')),
    down_mbps numeric,
    up_mbps numeric,
    data_cap_gb int,
    needs_hardware text check (needs_hardware in ('5g_router', 'dish')),
    unique (provider_id, external_key)
);

-- One row per scrape, append-only, so a price change stays answerable later.
create table plan_price (
    plan_id int not null references plan (id),
    observed_on date not null,
    monthly_eur numeric not null,
    setup_eur numeric,
    hardware_eur numeric,
    contract_months int,
    promo_months int,
    promo_monthly_eur numeric,
    primary key (plan_id, observed_on)
);

create view plan_current as
select distinct on (plan_id) *
from plan_price
order by plan_id, observed_on desc;
