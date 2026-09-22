-- One spelling of the word, the one the operators themselves print.
--
-- The schema was written in British English and the rest of the site is not. "fibre" sat in
-- two check constraints, a column on municipality_coverage and a field in the tiles. Stored
-- data and a published contract, then, rather than a comment anyone could just retype.

alter table technology drop constraint technology_family_check;
alter table plan drop constraint plan_family_check;

update technology set family = 'fiber' where family = 'fibre';
update plan set family = 'fiber' where family = 'fibre';
update coverage set family = 'fiber' where family = 'fibre';
update coverage_area set family = 'fiber' where family = 'fibre';
update address_coverage set family = 'fiber' where family = 'fibre';

alter table technology add constraint technology_family_check
    check (family in ('fiber', 'coax', 'copper', 'wireless', 'satellite', 'other'));
alter table plan add constraint plan_family_check
    check (family in ('fiber', 'coax', 'copper', 'wireless', 'satellite'));

-- speed_cell.family is 'fixed' or 'mobile' and means something else entirely. Left alone.

alter table municipality_coverage rename column fibre to fiber;
