-- Telekom, everywhere, and one row for it.
--
-- 0042 renamed the display and left the code as OTE, reasoning that the code is what the
-- register keys on. That was half a decision. The tile field, the filter button and the
-- API's provider code all read the code, so the site said OTE in four places and Telekom in
-- one. The register key is now held apart from the name we call them by.

update provider set code = 'TELEKOM' where code = 'OTE';

-- The register files four entities for one company: the incumbent, its UltraFast fiber arm
-- and the two rural concessions. Anyone shopping for a line is shopping from one company,
-- and a map that splits the coverage four ways understates all four of them. credited_to
-- says which provider a filing belongs to once it reaches a derived table. The alias rows
-- stay put, because register_id is how raw_* is joined and the register does file them
-- separately.
alter table provider add credited_to int references provider (id);

update provider set credited_to = (select id from provider where code = 'TELEKOM')
where code in ('OTE_ULTRAFAST', 'OTE_RURAL_NORTH', 'OTE_RURAL_SOUTH');

-- Who a reader can buy from.
--
-- Some operators file coverage and sell nothing to a household. The wholesale builders pass
-- premises for other people to retail over, and Metadosis files services but publishes no
-- tariff anyone can look up. Put beside Telekom and Vodafone they read as a supplier you
-- could pick, and there is nothing to pick. They are still worth drawing: fiber in the
-- ground decides whether anyone will ever sell you a gigabit here.
alter table provider add role text not null default 'retail'
    check (role in ('retail', 'infrastructure'));

update provider set role = 'infrastructure'
where code in ('FIBERGRID', 'UNITEDFIBER', 'FIBER2ALL', 'NETFIBER', 'METADOSIS');
