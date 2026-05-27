-- Their checker will not answer a bare street name: it wants the type with it, as its own
-- dropdown spells it, and returns "needs further investigation" for anything else. Case and
-- accent do not matter; the parenthesis does. The scrape recorded the type all along and
-- the ingest was dropping the column.
alter table raw_cosmote add street_type text;
