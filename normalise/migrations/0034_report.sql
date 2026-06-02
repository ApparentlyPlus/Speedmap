-- Where a price came from, because a figure read off a rate card and one quoted by the
-- provider's own ordering system are not the same claim. ΔΕΗ's card asks 60€ for a gigabit
-- while the market sells it near 20€, and a card is published rather than offered. Showing
-- both is fine; showing them as if they were the same thing is not.
alter table plan_price add source text not null default 'catalogue'
    check (source in ('catalogue', 'published'));

-- What someone told us we got wrong. Everything here is best effort, and the only way a
-- best effort improves is if the people who find the gaps have somewhere to put them.
-- Text is what a person typed, and is never read as anything else.
create table report (
    id bigserial primary key,
    kind text not null check (kind in ('availability', 'price', 'address', 'other')),
    detail text not null,
    address_id bigint references address (id) on delete set null,
    provider_id int references provider (id),
    plan_id int references plan (id),
    contact text,
    created_at timestamptz not null default now(),
    resolved_at timestamptz
);

-- The queue is what is still open, and it is read far more often than the whole table.
create index on report (created_at desc) where resolved_at is null;
