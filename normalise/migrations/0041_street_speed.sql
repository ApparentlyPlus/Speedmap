-- The fastest thing reaching any address on this street, for the dot beside it in search.
--
-- Derived rather than looked up: asking it at query time meant scanning every address on
-- the street and every coverage row under them, which took 173ms per keystroke against a
-- tier that otherwise answers in a third of a millisecond. A street's answer only changes
-- when the pipeline rebuilds, so it is computed when the pipeline rebuilds.
alter table street add best_mbps numeric;
