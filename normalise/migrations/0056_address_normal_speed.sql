-- The normally-available band, carried down to the address the same way the maximum is.
--
-- 0055 put it on coverage and coverage_area; the door route in 110 reads address_coverage,
-- which is built from both of those in 050 and had nowhere to put it. Without this the cap
-- is the maximum band on the door route and the normal band on the cabinet route, which is
-- two rules for one figure and exactly the shape of disagreement this pipeline keeps
-- getting bitten by.
--
-- Nullable and no default, so adding it to 12.8M rows is a catalogue change, not a rewrite.
alter table address_coverage add normal_band_id int references speed_band (id);

comment on column address_coverage.normal_band_id is
    'a4a_nordown: the normally available speed. speed_band_id is a4a_maxdown, the ceiling.';
