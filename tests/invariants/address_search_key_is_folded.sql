-- search_key is uppercased at ingest, so lowercase here means the fold was skipped.
select id, street, search_key
from address
where search_key <> upper(search_key);
