select c.id, c.technology, c.family, t.family as expected
from coverage_area c
join technology t on t.code = c.technology
where c.family <> t.family;
