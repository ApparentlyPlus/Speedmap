-- Greeklish needs a Latin form of the key it searches. Written at build time from the same
-- source as search_key, so street and locality both transliterate.
-- address and everything derived from it is rebuilt by normalise.build.
truncate address cascade;

alter table address add latin_key text not null;

create index on address (latin_key text_pattern_ops);
create index on address using gin (latin_key gin_trgm_ops);
