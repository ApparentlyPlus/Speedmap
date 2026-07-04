-- A street painted by a signal that reaches every street.
--
-- 5G covers nearly every address in the country and files a 300-1000 band wherever it does,
-- so counting it made 40,775 of the 40,796 streets that had a figure at all come out at
-- exactly 1000: one number, one colour, and a map that told the reader nothing. What a
-- street is asking about is the line that runs down it.
--
-- Caught here rather than by eye, because the symptom is a map that looks fine.
select s.id, s.name, s.best_mbps, sb.min_mbps, sb.max_mbps
from street s
join address a on a.municipality_id is not distinct from s.municipality_id
                 and a.street_fold = s.name_fold
join address_coverage ac on ac.address_id = a.id
join speed_band sb on sb.id = ac.speed_band_id
where ac.family = 'wireless'
  and s.best_mbps is not null
  and s.best_mbps > coalesce(
        (select max(coalesce(b.max_mbps, b.min_mbps))
         from address a2
         join address_coverage c2 on c2.address_id = a2.id
         join speed_band b on b.id = c2.speed_band_id
         where a2.municipality_id is not distinct from s.municipality_id
           and a2.street_fold = s.name_fold
           and c2.family <> 'wireless'), 0)
group by s.id, s.name, s.best_mbps, sb.min_mbps, sb.max_mbps;
