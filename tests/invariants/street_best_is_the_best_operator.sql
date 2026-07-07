-- A street painted one speed while claiming another for every operator on it.
--
-- The map colours a street by its best and filters it by the per-operator fields, and the
-- two are built by different steps over different joins. If they disagree the street is
-- painted a colour no operator on it can sell, which is the single most expensive class of
-- bug the prototype had: wrong, plausible, and silent.
select s.id, s.name, s.best_mbps, max(sp.mbps) as theirs
from street s
left join street_provider sp on sp.street_id = s.id
group by s.id, s.name, s.best_mbps
having s.best_mbps is distinct from max(sp.mbps);
