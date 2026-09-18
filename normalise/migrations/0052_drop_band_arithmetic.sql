-- Take out the two definitions 0049 added, which nothing reads any more.
--
-- 0049 made the map paint the band's assured speed held to what the line could carry. 0051
-- stopped reading the band at all: the figure is what the technology is sold at, and the
-- register's classes are not consulted. Everything 0049 built was for a question that is no
-- longer asked — the last reader of either went with 110 and 130.
--
-- Left in place they would be the most expensive kind of dead code: a generated column and
-- a function that both look like part of the speed pipeline, sitting next to the thing that
-- replaced them, waiting for somebody to reason from the wrong one. The band's floor is
-- still recoverable from min_mbps and max_mbps by anyone who wants it, and
-- technology.max_plausible_mbps stays where it is — the ranker still asks what a line can
-- carry, which is a different question from what it is retailed at.
drop view if exists speed_band_assured;
alter table speed_band drop column if exists assured_mbps;
drop function if exists held_to(numeric, numeric);
