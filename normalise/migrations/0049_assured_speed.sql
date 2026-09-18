-- What one number a filed band is worth, and what a technology can actually carry.
--
-- Two decisions, both about a map that read better than the country it describes, and both
-- needing one definition rather than the four copies of `coalesce(sb.max_mbps, sb.min_mbps)`
-- that were scattered across 110, 130 and two queries in api/main.py.
--
--
-- THE BAND IS WORTH ITS FLOOR, NOT ITS CEILING.
--
-- The register files classes, not speeds: there is no 137 Mbps in it, only "100-300". Every
-- consumer turned that into 300 — the top of the bucket — and 46,448 streets came out
-- painted 300 Mbps, every single one of them copper, not one with fibre behind it. 62% of
-- the country in the colour the ramp gives a gigabit-adjacent street, from vectored VDSL
-- cabinets filed at "100-300".
--
-- 300 is what the best line off that cabinet might get. 100 is what the band assures. For a
-- map that answers "what can I get here" the assured figure is the defensible one, and the
-- panel still shows the range in full, so nothing is hidden by showing the floor.
--
-- The note in NEEDTOKNOW had this under "looks like it would fix it and does not", on the
-- grounds that the distribution is identical and only the colour moves. That is true and it
-- is not the point: the distribution was never wrong, the claim was. What moves is 46,448
-- streets from "300 Mbps here" to "at least 100 Mbps here", and copper stops wearing a
-- colour that fibre should own.
--
-- Generated, so the four copies become one column nobody can spell differently.
-- coalesce, because the bottom band is open at the bottom — "< 0,2" has no floor — and
-- there its ceiling is the only number it has.
alter table speed_band add assured_mbps numeric
    generated always as (coalesce(min_mbps, max_mbps)) stored;

comment on column speed_band.assured_mbps is
    'The one number this band is worth: what it assures, not the best case in it.';


-- HELD TO WHAT THE LINE CAN CARRY.
--
-- The register files ADSL at 100-300 Mbps and at >= 1000, and VDSL above 100. Physically
-- impossible, faithfully carried, and it reached 1,061 ADSL-only streets and 712
-- plain-VDSL-only ones — painted speeds no line of that kind has ever delivered.
--
-- "Report as filed" was the standing decision and the reasoning was right: overriding the
-- regulator to make the map look sensible is the one thing this site should not do. What
-- that was protecting is the regulator's claim staying visible, not the map repeating a
-- physical impossibility — so the filing is kept and shown in the panel, and the figure the
-- map paints is held to what the technology can carry.
--
-- 130_municipality_coverage.sql already clamped and 110 did not, so a municipality's figure
-- and the streets inside it have been disagreeing about the same rows all along.
--
-- Two null cases, and getting either wrong is worse than not clamping at all:
--   - a band that was never filed must stay null. `least(null, 24)` is 24 in Postgres, so
--     the expression in 130 was quietly inventing 24 Mbps for every unfiled ADSL row.
--   - a technology with no ceiling — fibre, coax, wireless — must not be clamped to null.
create function held_to(mbps numeric, ceiling numeric) returns numeric
    language sql immutable parallel safe
    return case
        when mbps is null then null
        when ceiling is null then mbps
        else least(mbps, ceiling)
    end;

comment on function held_to(numeric, numeric) is
    'A filed speed, held to what the technology can carry. Null in stays null out.';
