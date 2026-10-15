-- painted one speed while every operator on it claims another
select s.id, s.name, s.best_mbps, max(sp.mbps) as theirs
from street s
left join street_provider sp on sp.street_id = s.id
group by s.id, s.name, s.best_mbps
having s.best_mbps is distinct from max(sp.mbps);
