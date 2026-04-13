-- The 333 Kallikratis municipalities, reprojected once so every later join is 4326.
insert into municipality (id, kallikratis_code, name, geom)
select gid, kalcode4, d1, geom4326::geography
from raw_dimos
where geom4326 is not null
on conflict (id) do update set
    kallikratis_code = excluded.kallikratis_code,
    name = excluded.name,
    geom = excluded.geom;
