-- A cache row that expires before it was observed is never servable.
select address_id, provider_id, technology, observed_at, expires_at
from availability
where expires_at <= observed_at;
