-- Cabinet areas get the same planar twin as municipalities, for the same reason: matching
-- 1.5M addresses against 75,793 polygons is containment, not distance.
alter table coverage_area add geom_2d geometry(MultiPolygon, 4326)
    generated always as (geom::geometry) stored;

create index on coverage_area using gist (geom_2d);

-- What is available at an address. Fibre and coax arrive through the point link; copper
-- through the cabinet polygon the address falls inside.
create table address_coverage (
    address_id bigint not null references address (id) on delete cascade,
    provider_id int not null references provider (id),
    technology text not null references technology (code),
    infra_provider_id int references provider (id),
    speed_band_id int references speed_band (id),
    family text not null,
    matched_by text not null check (matched_by in ('point', 'area')),
    avail_date date,
    primary key (address_id, provider_id, technology)
);
