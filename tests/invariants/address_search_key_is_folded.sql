-- search_key is uppercased at ingest. Lowercase here means the fold was skipped.
select id, street, search_key
from address
where search_key <> upper(search_key);
