-- The response as it arrived, kept so a broken parser can be re-run against history rather
-- than re-scraped. When a site is redesigned the question is always the same: what changed
-- in the shape between the last success and the first failure. Without the bodies that is
-- unanswerable and the only way forward is to guess.
--
-- Not kept for every attempt. A nightly sweep of two hundred addresses would store tens of
-- megabytes of identical HTML for no benefit; the bodies that matter are the ones that
-- broke, and the canaries, whose whole purpose is to be compared over time.
alter table probe_attempt add raw text;
