-- Concurrently, so a rebuild never blanks the relation the probe layer is reading.
refresh materialized view concurrently wholesale;
