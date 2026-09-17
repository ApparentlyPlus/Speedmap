-- Which line reaches a street, kept apart from how fast it is claimed to be.
--
-- These were one number until now: the figure was what the technology is sold at, so the
-- figure and the line were the same fact and the colour could be read off the speed.
--
-- Capping the figure at what the operator filed breaks that. A vectored cabinet filed
-- "2-10 Mbps" is now worth 10, and so is an ADSL one filed the same way — same number,
-- different line, and a map painted by the number would call the first one ADSL. About 8%
-- of streets land on a figure their own technology would never have given them.
--
-- So the two are stored separately and each is used for the one thing it answers: the line
-- is what the street is coloured by and what the legend names, the figure is what the panel
-- and the search dot report. Neither stands in for the other.
--
-- A rank on the technology, because "best" has to mean something to `max` and the codes do
-- not sort usefully — FTTH would beat VECT_VDSL by luck and VDSL would beat both.
alter table technology add rank smallint;

comment on column technology.rank is
    'How good this kind of line is, for picking the best one reaching a place. Higher wins.';

update technology set rank = v.rank from (values
    ('ADSL', 1), ('VDSL', 2), ('VECT_VDSL', 3), ('DOCSIS', 4), ('FTTH', 5),
    -- Wireless is ranked so an address panel can order it, and never competes for a street:
    -- the street map leaves mobile out entirely.
    ('FWA_4G', 1), ('FWA_5G', 2), ('SAT', 1)
) as v (code, rank) where technology.code = v.code;

-- The best line reaching this street, as the technology code. A string rather than the rank,
-- because it travels into the vector tile and is read there by a `match` expression: a tile
-- that says "FTTH" can be debugged by looking at it, and one that says 5 cannot.
alter table street add best_line text references technology (code);

-- The same, per operator, since the map filters to one at a time and a filtered street must
-- wear that operator's line rather than the best line anyone has.
alter table street_provider add line text references technology (code);
