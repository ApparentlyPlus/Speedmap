-- The prefix indexes carry the house number, so a search page can be chosen from the index
-- alone.
--
-- The prefix tier picks the best eight doors of everything under a prefix, ordered by the
-- number the reader typed, then by size. Two letters cover 77,000 doors, and choosing among
-- them read every one from the table, because the number was not in the index: 31,000 blocks
-- per keystroke, which on an SD card is the difference between typing and waiting. With it
-- included the choice is an index-only scan and the table is read for the eight it keeps.
drop index address_prefix_search;
drop index address_prefix_latin;

create index address_prefix_search on address
    (search_key text_pattern_ops, premises desc nulls last, id) include (street_no)
    where street <> '-';
create index address_prefix_latin on address
    (latin_key text_pattern_ops, premises desc nulls last, id) include (street_no)
    where street <> '-';
