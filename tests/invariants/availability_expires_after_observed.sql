-- A cache row that expires before it was observed can never be served.
select address_id, provider_id, technology, observed_at, expires_at
from availability
where expires_at <= observed_at;
