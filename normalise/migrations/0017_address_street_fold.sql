-- address_key used street verbatim, so ΑΧΑΡΝΩΝ and Αχαρνών were two rows for one building:
-- 59,899 duplicates, 3.9% of the index. Identity is the folded street, which also collapses
-- ΛΕΩΦ. ΑΛΕΞΑΝΔΡΑΣ into ΑΛΕΞΑΝΔΡΑΣ, because a type word is not identity.
-- address and everything derived from it is rebuilt by normalise.build, never hand-edited.
truncate address cascade;

alter table address add street_fold text not null;
alter table address drop constraint address_key;
alter table address add constraint address_key
    unique nulls not distinct (postcode, street_fold, street_no, municipality_id);

create index on address (street_fold);
