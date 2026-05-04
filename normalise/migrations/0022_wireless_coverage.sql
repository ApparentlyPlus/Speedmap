-- A cell reports one speed band across every technology it carries, so the band belongs to
-- the best generation present rather than to each separately. Hence one row per address and
-- provider, named for that generation, instead of one per flag.
insert into technology (code, family) values
    ('FWA_4G', 'wireless'),
    ('FWA_5G', 'wireless');

alter table address_coverage drop constraint address_coverage_matched_by_check;

alter table address_coverage add constraint address_coverage_matched_by_check
    check (matched_by in ('point', 'area', 'cell'));
