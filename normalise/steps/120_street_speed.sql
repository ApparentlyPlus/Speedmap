-- best speed per street, from street_provider so it matches the operator filter
update street s
set best_mbps = top.mbps
from (
    select st.id, max(sp.mbps) as mbps
    from street st
    left join street_provider sp on sp.street_id = st.id
    group by st.id
) top
where top.id = s.id
  and s.best_mbps is distinct from top.mbps;
