-- The register files speed as one of eight bands, never a number, and omits it on
-- 73.3% of services. A null band means not filed; it never means slow.
create table speed_band (
    id int primary key,
    min_mbps numeric,
    max_mbps numeric,
    label text not null
);

-- Bands 1 and 8 are open ended, so one bound each is genuinely unknown.
insert into speed_band (id, min_mbps, max_mbps, label) values
    (1, null, 0.2, '< 0,2 Mbps'),
    (2, 0.2, 2, '0,2-2 Mbps'),
    (3, 2, 10, '2-10 Mbps'),
    (4, 10, 30, '10-30 Mbps'),
    (5, 30, 100, '30-100 Mbps'),
    (6, 100, 300, '100-300 Mbps'),
    (7, 300, 1000, '300-1000 Mbps'),
    (8, 1000, null, '>= 1000 Mbps');

-- The register's own technology ids, so normalise joins rather than hardcodes a map.
alter table technology add register_id int unique;

alter table technology drop constraint technology_family_check;
alter table technology add constraint technology_family_check
    check (family in ('fibre', 'coax', 'copper', 'wireless', 'satellite', 'other'));

insert into technology (code, family, max_plausible_mbps) values ('OTHER', 'other', null);

update technology set register_id = v.register_id from (values
    ('ADSL', 1), ('VDSL', 2), ('VECT_VDSL', 3), ('FTTH', 4), ('DOCSIS', 5), ('OTHER', 13)
) as v (code, register_id) where technology.code = v.code;

-- Speed becomes a band everywhere the register is the source.
alter table coverage drop column max_down_mbps;
alter table coverage add speed_band_id int references speed_band (id);

alter table coverage_area drop column max_down_mbps;
alter table coverage_area add speed_band_id int references speed_band (id);

-- availability keeps its numeric column: a live checker answers with a real number,
-- while a register-sourced row carries a band.
alter table availability add speed_band_id int references speed_band (id);
