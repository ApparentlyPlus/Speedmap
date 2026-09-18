-- Whether the attempt was one the operator could have answered.
--
-- Every exception out of an adapter was recorded the same way: ok = false, counted against
-- the operator by probe/health.py, and shown to the reader as the checker being degraded.
-- Two of those failures are not about the operator at all.
--
-- Both adapters that want an address in words want it in their own spelling, and we hold
-- that spelling only for the streets the Cosmote scrape walked — 43% of streets, though
-- 86% of addresses, since addresses cluster on the streets it did walk. Πατησίων is not
-- among them. Handed one of the rest, the adapter reports that it cannot look the address
-- up, which is the correct thing for it to do, and was then counted as the operator
-- failing to answer.
--
-- The effect was live and visible: on 19 September every request OTE and Vodafone actually
-- made succeeded, and both were showing as degraded because the sweep had also handed them
-- addresses with no spelling. It is the same mistake as reporting "has not answered since"
-- about an operator that had answered — our own gap, worn by somebody else.
--
-- Recorded rather than dropped: how often we cannot ask is worth knowing, and is a fact
-- about the address book. It is simply not evidence about the checker.
alter table probe_attempt add askable boolean not null default true;

comment on column probe_attempt.askable is
    'False when the address could not be put to the operator at all — our gap, not theirs.';
