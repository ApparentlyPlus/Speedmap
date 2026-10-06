-- Where most of each street's doors say they are, for the search list. It used to be a
-- mode() over every door of every listed street, per keystroke. mode() takes the first of
-- equally common values in its order, so this gives the same answer.
update street s
set locality = found.locality
from (
    select st.id, doors.locality
    from street st
    left join (
        select street_id, mode() within group (order by locality) as locality
        from address
        where street_id is not null and locality is not null
        group by street_id
    ) doors on doors.street_id = st.id
) found
where found.id = s.id
  and s.locality is distinct from found.locality;
