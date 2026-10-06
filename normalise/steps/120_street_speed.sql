-- The best anyone sells down this street, for the map colour and the search dot. Read off
-- street_provider so the colour and the operator filter agree.
--
-- The update clears too. It used to only write, so a street kept a figure granted under an
-- older, looser rule forever.
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
