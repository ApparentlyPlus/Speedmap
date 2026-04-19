-- Municipality lookup is containment, never distance, and planar containment is 31x faster
-- than the spheroid form: 40.6s against 1.3s per 100k points, with zero disagreements over
-- 200,000 real points. Generated, so the two representations cannot drift apart.
alter table municipality add geom_2d geometry(MultiPolygon, 4326)
    generated always as (geom::geometry) stored;

create index on municipality using gist (geom_2d);
