-- started_at recorded when the row was created, not when a run began, so anything derived
-- from it was wrong for every resumed dataset. Split the two apart.
alter table register_fetch rename column started_at to created_at;
alter table register_fetch add run_started_at timestamptz;
alter table register_fetch add run_fetched integer not null default 0;

-- fetched is the cumulative position in the dataset; run_fetched is this run's work, which
-- is the only one of the two that divides into a meaningful rate.
create view register_progress as
select
    dataset,
    fetched,
    total,
    round(100.0 * fetched / nullif(total, 0), 1) as pct,
    date_trunc('second', now() - run_started_at) as running_for,
    round(60 * run_fetched / nullif(extract(epoch from now() - run_started_at), 0)) as rows_per_min,
    make_interval(secs => round(
        (total - fetched) / nullif(run_fetched / nullif(extract(epoch from now() - run_started_at), 0), 0)
    )) as eta
from register_fetch;
