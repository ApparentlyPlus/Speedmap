-- Which street an address sits on.
--
-- The join used to be by name: municipality plus folded street name, worked out afresh in
-- three places. That held up while a street was every road of that name in the
-- municipality, because there was only ever one row to find. A street is one connected road
-- now, so the same join finds every component of the name at once. A filing against a door
-- at one end of town would be credited to a road of the same name at the other, which is
-- the bleeding the split was made to stop.
--
-- 065 pins the address to the nearest component instead, once.
alter table address add street_id bigint references street (id) on delete set null;

create index address_street_idx on address (street_id);

-- The lookup 065 makes, 1.14 million times.
create index street_municipality_name_idx on street (municipality_id, name_fold);
