-- Which step put each derived row here, so a step can clear its own work and no more.
--
-- "Build steps that only ever write are a trap" was already written down about
-- 110_street_speed.sql, which filled nulls and never cleared, so streets kept figures
-- granted under looser rules forever — 3,189 of them still painted from district-wide
-- filings months after those stopped being allowed to name a street. The note ends "check
-- any step you tighten for the same shape". Every other step has the same shape.
--
-- 030, 040, 050, 070 and 100 are all `insert ... on conflict do update` with no delete
-- anywhere. Nothing is wrong today because the register has been pulled exactly once. The
-- first re-pull is where it bites: an operator that withdraws a filing has it removed from
-- raw_wiredservice and keeps it in coverage, address_coverage and therefore on the map,
-- with no row anywhere recording that it ever left. There is a last_seen column on coverage
-- that was clearly meant for this and nothing reads it.
--
-- A step cannot just truncate what it writes, because three steps share address_coverage:
-- 050 files the register's points and cabinets, 070 the wireless grid, 100 the builders who
-- retail their own fibre and file no service. 050 and 100 both write matched_by 'point', so
-- there is no existing column that tells their rows apart.
--
-- Nullable and no default, so adding it to 12.7M rows is a catalogue change rather than a
-- rewrite. Rows already here carry null, which no step claims and no step will delete; the
-- next full build stamps them.
alter table address_coverage add built_by text;

comment on column address_coverage.built_by is
    'The normalise step that inserted this row. A step clears its own and leaves the rest.';

-- Small and very unselective — three values over 12.7M rows — so it earns its place only
-- because the delete at the head of each step is a full-table operation without it.
create index address_coverage_built_by_idx on address_coverage (built_by);
