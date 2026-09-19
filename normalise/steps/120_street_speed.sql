-- The best anyone sells down this street, for the map colour and the search dot. Read off
-- street_provider rather than derived again, so the colour and the operator filter agree.
--
-- Cleared by the update itself: this used to only ever write, so a street kept a figure
-- granted under a looser rule for ever.
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
