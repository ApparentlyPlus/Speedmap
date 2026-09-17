-- What a municipality looks like under each of the three views, not just the first one.
--
-- The choropleth is the map's only answer at the zooms where a street is a fraction of a
-- pixel, and it had exactly one figure: the share of addresses fibre reaches, which is a
-- filed claim. Drawn under Measured and under Mobile it put a filed claim beneath a
-- measured map — the one thing this codebase is otherwise careful never to do, since the
-- whole reason Filed and Measured are separate views is that they are separate claims.
--
-- So the region carries a figure per view and the layer paints whichever view is on.
--
-- Measured is weighted by tests, not a plain average of cells. A municipality with one cell
-- of 900 Mbps from two tests and forty cells of 30 Mbps from five hundred each is a 30 Mbps
-- municipality, and the plain mean calls it 50. The weight is the only thing standing
-- between a choropleth and its loudest outlier.
--
-- Nullable, and null far more often than not: about four per cent of the country has ever
-- been speed-tested, so most municipalities have no measurement under either family. That
-- is the normal case and the layer draws it as unmeasured rather than as nought.
alter table municipality_coverage add measured_mbps numeric;
alter table municipality_coverage add measured_tests integer;
alter table municipality_coverage add mobile_mbps numeric;
alter table municipality_coverage add mobile_tests integer;

comment on column municipality_coverage.measured_mbps is
    'Fixed-line speed tests in this municipality, weighted by how many tests each cell holds.';
comment on column municipality_coverage.mobile_mbps is
    'The same for mobile, kept apart because the two measure different things.';
