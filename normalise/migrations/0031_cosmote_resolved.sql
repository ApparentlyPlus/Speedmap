-- Where each scraped row landed in our own hierarchy. The build works both out already and
-- threw them away, which left the operator's own spelling of a street unreachable: only 164
-- of their 506 dimoi share a name with a Καλλικράτης municipality, so a probe cannot
-- construct what to send them and has to be told.
alter table raw_cosmote add municipality_id int references municipality (id);
alter table raw_cosmote add street_fold text;

create index on raw_cosmote (municipality_id, street_fold);
