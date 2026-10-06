-- concurrently, so a rebuild never blanks the view while the probes read it
refresh materialized view concurrently wholesale;
