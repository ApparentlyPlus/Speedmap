-- A street is one road. Every road of that name in the municipality was one row.
--
-- Streets were grouped by folded name and municipality alone, so ΜΗΤΡΟΠΟΛΕΩΣ in a
-- municipality that has two of them came out as a single row holding both. 7,631 rows were
-- two or more roads that never touch, 516 of them spanning more than 20 km and one spanning
-- 674. A cabinet reaching one of those roads coloured all of them, and a camera fitted to
-- the row's bounding box framed the gap in between.
--
-- Ways are clustered into connected runs first now, and each run is its own street. Name
-- and municipality no longer identify a row by themselves, so the component index joins
-- the key.
alter table street add component int not null default 0;

alter table street drop constraint street_sort_key_municipality_id_key;
alter table street add constraint street_sort_key_municipality_id_component_key
    unique nulls not distinct (sort_key, municipality_id, component);
