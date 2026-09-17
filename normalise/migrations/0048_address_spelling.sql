-- The distinct things an address can be searched by, once each.
--
-- The fuzzy tier is the one that answers a typo, and it was the slowest thing on the site by
-- an order of magnitude: 600-750ms, against a prefix tier that answers in under one. It ran
-- `search_key % '…'` over all 1.8M address rows, and a GIN trigram index cannot decide `%`
-- from the index alone — it hands back every row sharing enough trigrams and the executor
-- rechecks each one. For one measured query that was 164,930 candidates fetched across
-- 18,503 heap blocks to return 128 rows, of which 8 were wanted.
--
-- The work is almost all repetition. 1.8M addresses carry 126,194 distinct search keys and
-- 36,196 distinct street folds: Πατησίων in Αθήνα is one question asked nine hundred times.
-- Matched once per distinct key it is a 126K-row problem, and 126K rows fit in memory.
--
-- Raising pg_trgm.similarity_threshold was tried and is not the answer: at 0.4 the query
-- that took 600ms takes 250 and returns nothing at all, because the matches a typo actually
-- produces sit below it. The cost has to come out of the row count, not the recall.
--
-- Named for the spelling rather than the key, because address_key is already an index on
-- address and Postgres keeps both in one namespace.
-- A materialized view rather than a table, because it is a projection of address and must
-- never be able to disagree with it; refreshed by 020_address, which is what changes it.
create materialized view address_spelling as
select search_key, latin_key
from address
where street <> '-'
group by search_key, latin_key;

-- Unique, so the refresh can be `concurrently` and a rebuild never blanks the relation the
-- search is reading. The pair is the key: one spelling folds to one of each by construction.
create unique index address_spelling_key on address_spelling (search_key, latin_key);

-- Both alphabets, both ways of asking. The trigram indexes are what the fuzzy tier rides;
-- the pattern ones let the same view answer the prefix and word tiers if they ever move here.
create index address_spelling_search_trgm on address_spelling using gin (search_key gin_trgm_ops);
create index address_spelling_latin_trgm on address_spelling using gin (latin_key gin_trgm_ops);

-- One index for both halves of the search, on each alphabet.
--
-- text_pattern_ops, so it serves `like 'ΑΓ%'` as well as `=`: the prefix tier needs the
-- first and the fuzzy tier's join back from address_spelling needs the second, and a
-- default-collation btree cannot do the first at all outside the C locale.
--
-- Partial on `street <> '-'`, which is the register's 70 nameless addresses. As a filter it
-- forced every candidate row out of the heap to be checked; as a predicate it is free, and
-- the scan becomes index-only.
--
-- The trailing columns are the suggestion list's order, so the top eight of a prefix that
-- matches 182,000 rows come off the index instead of out of a sort over all of them. A
-- two-letter prefix — which is what the reader has typed after two keystrokes, and so the
-- commonest query there is — went from 79ms to 15ms, and from 20,122 heap blocks to none.
create index address_prefix_search on address
    (search_key text_pattern_ops, premises desc nulls last, id) where street <> '-';
create index address_prefix_latin on address
    (latin_key text_pattern_ops, premises desc nulls last, id) where street <> '-';
