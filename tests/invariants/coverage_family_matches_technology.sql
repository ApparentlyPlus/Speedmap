-- family is defined on technology
select c.id, c.technology, c.family, t.family as expected
from coverage c
join technology t on t.code = c.technology
where c.family <> t.family;
