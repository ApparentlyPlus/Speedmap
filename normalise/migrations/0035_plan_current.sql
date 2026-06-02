-- The view was written with a star, and Postgres resolves one at creation: every column
-- added to plan_price since has been invisible through it, silently. Named columns instead,
-- so the next addition fails loudly here rather than going missing.
drop view plan_current;

create view plan_current as
select distinct on (plan_id)
    plan_id, observed_on, monthly_eur, setup_eur, hardware_eur,
    contract_months, promo_months, promo_monthly_eur, source
from plan_price
order by plan_id, observed_on desc;
