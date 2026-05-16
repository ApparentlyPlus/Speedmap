-- Who sells over whose infrastructure, taken from what the register already records rather
-- than written down from the trade press: the filings are the agreement in evidence, and
-- they stay current as the register does. A single filing nationwide is a data error, not a
-- wholesale deal, so a relationship has to be filed a few dozen times to count.
-- Families are pooled deliberately. Copper unbundling and fibre VULA are different products,
-- but a wholesale relationship between two operators is a commercial fact rather than a
-- per-technology one, and the register files Nova over OTE fibre only 83 times while filing
-- the same pair on copper 16,232 times. Reading those separately would deny an agreement
-- that plainly exists.
create view wholesale as
select infra_provider_id as infra_id, provider_id as seller_id, count(*) as filings
from (
    select infra_provider_id, provider_id from coverage
    union all
    select infra_provider_id, provider_id from coverage_area
) filed
where infra_provider_id is not null and infra_provider_id <> provider_id
group by 1, 2
having count(*) >= 50;

-- Street-level questions are asked per municipality and folded name, which the address key
-- cannot serve: it leads on postcode, and the scrape files none.
create index on address (municipality_id, street_fold);
