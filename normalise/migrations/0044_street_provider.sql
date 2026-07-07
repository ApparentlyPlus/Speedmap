-- The best each operator reaches on each street.
--
-- street.best_mbps is the best anyone reaches, which is the right colour for a street but
-- the wrong answer to "who can I buy from here". The map filters by operator, and a filter
-- over a single best paints a street in one operator's colour while claiming another's.
--
-- A table rather than a column per operator: the set of them changes — Inalan, ΔΕΗ and HCN
-- all arrived after the register's schema was fixed, and Metadosis is retailing with no
-- tariff we hold yet. A column per operator makes every new one a migration, and the tile
-- builder pivots this into its own flat fields anyway, where the names are a contract.
create table street_provider (
    street_id integer not null references street (id) on delete cascade,
    provider_id integer not null references provider (id),
    mbps numeric,
    primary key (street_id, provider_id)
);

create index street_provider_provider_idx on street_provider (provider_id);
