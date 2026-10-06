-- A street painted one speed while every operator on it claims another.
--
-- The map colours a street by its best and filters it by per-operator fields. If the two
-- disagree the street wears a colour nobody on it sells. That was the prototype's costliest
-- class of bug: wrong, plausible and silent.
select s.id, s.name, s.best_mbps, max(sp.mbps) as theirs
from street s
left join street_provider sp on sp.street_id = s.id
group by s.id, s.name, s.best_mbps
having s.best_mbps is distinct from max(sp.mbps);
