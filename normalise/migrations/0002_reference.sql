-- How strongly a fact is held: measured by a speed test, declared by an operator
-- filing or advertising it, or inferred by us from a join.
create type assertion as enum ('measured', 'declared', 'inferred');

create table provider (
    id serial primary key,
    code text unique not null,
    display_name text not null,
    kind text not null check (kind in ('incumbent', 'altnet', 'mno', 'satellite')),
    builds_own_network boolean not null default false
);

create table source (
    name text primary key,
    url text,
    licence text,
    last_run_at timestamptz,
    last_ok_at timestamptz
);

-- One definition of each access technology. max_plausible_mbps is the physical
-- ceiling the ranker clamps to; the register files rows above it, which are kept
-- verbatim in coverage and only corrected at ranking time.
create table technology (
    code text primary key,
    family text not null
        check (family in ('fibre', 'coax', 'copper', 'wireless', 'satellite')),
    max_plausible_mbps numeric
);

insert into technology (code, family, max_plausible_mbps) values
    ('FTTH', 'fibre', null),
    ('DOCSIS', 'coax', null),
    ('VECT_VDSL', 'copper', 300),
    ('VDSL', 'copper', 100),
    ('ADSL', 'copper', 24),
    ('FWA', 'wireless', null),
    ('SAT', 'satellite', null);
