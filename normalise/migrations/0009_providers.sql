-- The register's provider ids, and our own classification of them.
alter table provider add register_id int unique;

-- builds_own_network is not a guess: these are exactly the operators that appear as
-- infrprov on the register's 2.67M infrastructure points.
insert into provider (register_id, code, display_name, kind, builds_own_network) values
    (1, 'OTE', 'OTE', 'incumbent', true),
    (2, 'VODAFONE', 'Vodafone', 'mno', false),
    (3, 'UNITEDFIBER', 'UnitedFiber', 'altnet', true),
    (4, 'TISPARKLE', 'TI Sparkle Greece', 'altnet', false),
    (5, 'INALAN', 'INALAN', 'altnet', true),
    (6, 'OTE_RURAL_NORTH', 'OTE Rural North', 'incumbent', false),
    (7, 'OTE_RURAL_SOUTH', 'OTE Rural South', 'incumbent', false),
    (8, 'RURAL_CONNECT', 'Rural Connect', 'altnet', false),
    (9, 'HCN', 'HCN', 'altnet', true),
    (10, 'GRID', 'GRID', 'altnet', false),
    (11, 'FIBAIR', 'FIBAIR', 'altnet', false),
    (12, 'OPTILAND', 'OPTILAND', 'altnet', false),
    (13, 'FIBERGRID', 'FIBERGRID', 'altnet', true),
    (14, 'DEDDIE', 'ΔΕΔΔΗΕ', 'altnet', false),
    (15, 'NOVA', 'Nova', 'mno', false),
    (16, 'FIBER2ALL', 'Fiber2All', 'altnet', true),
    (17, 'DIGEA', 'DIGEA', 'altnet', false),
    (18, 'FAST_TELECOM', 'FAST Telecom', 'altnet', false),
    (19, 'METADOSIS', 'Metadosis', 'altnet', false),
    (20, 'NETFIBER', 'NETFIBER', 'altnet', true),
    (21, 'DEI', 'ΔΕΗ', 'altnet', false),
    (22, 'OTE_ULTRAFAST', 'OTE UltraFast', 'incumbent', true),
    (23, 'ORIZON', 'ORIZON Telecom', 'altnet', false),
    (24, 'LANCOM', 'Lancom', 'altnet', false);

-- Who built the line is not who sells it: FIBERGRID passes 811,123 premises and files
-- no service at all, while Vodafone files 856,733 services over other operators' fibre.
alter table coverage add infra_provider_id int references provider (id);
alter table coverage_area add infra_provider_id int references provider (id);
