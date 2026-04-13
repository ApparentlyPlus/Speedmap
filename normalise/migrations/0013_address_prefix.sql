-- Type-ahead is a prefix search, not a similarity search. Ordering 1.5M rows by
-- similarity() scans 28,441 candidates for eight results and takes 445ms; the same
-- lookup as a prefix takes 0.3ms. text_pattern_ops so LIKE 'X%' uses the index whatever
-- the database collation is.
create index address_search_key_prefix on address (search_key text_pattern_ops);
