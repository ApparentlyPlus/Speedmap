-- The relation is tiny and the query behind it is not: it aggregates every coverage filing
-- in the country, which cost 80ms on a path that otherwise answers in a third of a
-- millisecond. Stored and refreshed with the rest of the build instead.
drop view wholesale;

create materialized view wholesale as
select infra_provider_id as infra_id, provider_id as seller_id, count(*) as filings
from (
    select infra_provider_id, provider_id from coverage
    union all
    select infra_provider_id, provider_id from coverage_area
) filed
where infra_provider_id is not null and infra_provider_id <> provider_id
group by 1, 2
having count(*) >= 50;

create unique index on wholesale (infra_id, seller_id);
create index on wholesale (seller_id);
