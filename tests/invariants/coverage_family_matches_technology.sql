-- family is stored on coverage but defined on technology. They must agree.
select c.id, c.technology, c.family, t.family as expected
from coverage c
join technology t on t.code = c.technology
where c.family <> t.family;
