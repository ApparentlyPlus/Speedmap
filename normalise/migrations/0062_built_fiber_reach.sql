-- How near built fiber has to stand to a street to be about that street, in one place.
--
-- 110 places a builder's filing against the nearest street when the register named no
-- address for it, and the invariant that checks where a street's figure came from has to
-- cut at the same distance. Two copies of 100 that have to agree, with nothing making them,
-- is what cabinet_m2() already exists to avoid.
--
-- 100 m. The median unaddressed filing sits 68 m from its road and two thirds of the
-- premises behind them are inside 100. The tail runs long, p90 at 496 m and p99 at 2.8 km,
-- because a point up a mountain is nearest to a road it has nothing to do with. Widening
-- the cut to catch those buys coverage by inventing it. What falls outside stays unplaced.
create function built_fiber_m() returns double precision
    language sql immutable parallel safe
    return 100::double precision;

comment on function built_fiber_m() is
    'How near built fiber stands to the street it is credited to, in metres.';
