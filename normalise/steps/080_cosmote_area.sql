-- Learned only from the rows the scrape placed on a roof or interpolated along a street.
-- Locality precision drops the point in the town centre, which is the wrong municipality
-- often enough to poison the vote, and those rows are the ones that most need the answer.
insert into cosmote_area (dimos, area, municipality_id, placed)
select distinct on (c.dimos, coalesce(c.area, ''))
    c.dimos, coalesce(c.area, ''), m.id, count(*)
from raw_cosmote c
join municipality m on st_contains(m.geom_2d, c.geom::geometry)
where c.geocode_precision in ('rooftop', 'interpolated')
group by c.dimos, coalesce(c.area, ''), m.id
order by c.dimos, coalesce(c.area, ''), count(*) desc
on conflict (dimos, area) do update set
    municipality_id = excluded.municipality_id,
    placed = excluded.placed;
