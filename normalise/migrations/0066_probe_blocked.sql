-- Whose bot protection answered instead of the operator, when one did: Imperva, Cloudflare or
-- a rate limit. Null on every other attempt.
--
-- A block isn't about the address it happened on. It's about us, so the whole operator rests
-- for a while and every reader is shown what the cache holds. Recorded per attempt, so the
-- rest can grow with each block in a row and the health check can say whose wall it was.
alter table probe_attempt add column blocked text;
