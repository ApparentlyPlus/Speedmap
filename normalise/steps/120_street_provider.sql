-- One row per operator per street, from the addresses on it.
--
-- Runs after every source of coverage, including the builders of step 100: one of them
-- passes 112,739 addresses and files no retail service at all, so a street of theirs would
-- otherwise be blank for them while showing a gigabit for somebody else.
--
-- The topmost band is open-ended and files no ceiling, so its floor stands in for it, the
-- same rule the street's overall best uses. Null mbps is an operator that reaches the
-- street and filed no speed, which is the commonest state in the register and is not zero.
truncate street_provider;

-- Fixed lines only, for the same reason the street's own figure leaves mobile out: an
-- operator whose 5G reaches everywhere is not an operator that reaches this street, and a
-- filter that said so would show the whole country under every mobile network.
insert into street_provider (street_id, provider_id, mbps)
select s.id, ac.provider_id, max(coalesce(sb.max_mbps, sb.min_mbps))
from street s
join address a on a.municipality_id = s.municipality_id and a.street_fold = s.name_fold
join address_coverage ac on ac.address_id = a.id
left join speed_band sb on sb.id = ac.speed_band_id
where ac.family <> 'wireless'
group by s.id, ac.provider_id;
