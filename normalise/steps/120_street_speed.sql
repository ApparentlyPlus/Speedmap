-- The best anyone can sell down this street, for the colour on the map and the dot in
-- search.
--
-- Taken from street_provider rather than derived a second time from the coverage tables.
-- The map colours a street by this and filters it by the per-operator fields built in 110,
-- and when those were two separate walks over two different joins they disagreed on 42% of
-- the country: a street painted a speed no operator on it could sell, which is the single
-- most expensive class of bug the prototype had — wrong, plausible, and silent.
--
-- One derivation feeding the other makes tests/invariants/street_best_is_the_best_operator
-- true by construction. There is nothing left for the two to disagree about.
--
-- Cleared first, so the step recomputes rather than fills in. Both statements here only
-- ever wrote a figure, so a street that qualified under a looser rule kept what that rule
-- gave it forever and tightening anything changed nothing — that is how 3,189 streets went
-- on being painted from district-wide filings after those stopped being allowed to name a
-- street. Check any step you tighten for the same shape.
update street s
set best_mbps = best.mbps
from (
    select st.id, max(sp.mbps) as mbps
    from street st
    left join street_provider sp on sp.street_id = st.id
    group by st.id
) best
where best.id = s.id
  and s.best_mbps is distinct from best.mbps;
