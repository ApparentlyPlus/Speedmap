-- Who reaches each street, and how fast — the one place that question is answered.
--
-- This used to be two steps deriving the same thing two ways. The street's own figure came
-- from the addresses on it, falling back to the cabinets it crosses when it had none; the
-- per-operator figures came from the addresses alone. They disagreed on 33,760 streets —
-- 42% of the country — every one of them painted a colour on the map with no operator row
-- behind it, so the street glowed under "any operator" and vanished the moment a reader
-- pressed one. tests/invariants/street_best_is_the_best_operator.sql is written against
-- exactly that and had been failing against the real database the whole time; it only ever
-- ran against the fixture.
--
-- Two derivations that have to agree and nothing making them is the same shape as the tile
-- field names and the cabinet cap, and it is fixed the same way: derive one thing once, and
-- let everything else read it. street_provider is built here and 120 takes the street's
-- figure from it, so the two cannot disagree — the invariant is true by construction rather
-- than by two queries happening to match.
--
-- After every source of coverage is in, including the builders who retail their own fibre
-- and file nothing: those are step 100, and a street of theirs would otherwise read as
-- having no speed at all.
truncate street_provider;

-- Both ways an operator can reach a street, because there are two and only one was asked.
--
-- The doors are the filings at the addresses on it. The areas are the cabinets it runs
-- through. An operator that files doors and no areas — which is every builder, INALAN among
-- them with 112,739 addresses and not one polygon — cannot appear from the areas; a street
-- with no door on it at all, which is half of them, cannot appear from the doors. The
-- street panel in api/main.py has unioned both since "Ask both ways an operator can reach
-- a street", and this is the same union, so the colour, the filter and the panel are three
-- readings of one answer instead of three answers.
--
-- Fixed lines only. 5G reaches nearly every address in the country and files a 300-1000
-- band wherever it does; counted here it made 40,775 of the 40,796 streets that had a
-- figure come out at exactly 1000 — one number, one colour, no information. What a street
-- is asking about is the line that runs down it. Guarded by tests/invariants/.
--
-- The figure is what the line is retailed at, capped by what the operator filed for it:
-- least(sold_mbps, the band's ceiling). Technology is the anchor and the filing can only
-- ever pull it down, never lift it.
--
--   * technology.sold_mbps rather than max_plausible_mbps, because the ceiling is physics
--     and this is a shop: every VDSL plan in Greece is 50 whatever the cable could do, and
--     all three retailers sell vectoring at exactly 100 and none at 300. Migration 0051.
--   * capped, because an ADSL cabinet filed "0,2-2 Mbps" is an operator telling us this
--     particular line is bad, and that is worth more than the national retail figure.
--   * the band's CEILING and not its floor, because both sides of the least() are then
--     "the most you can get" claims and the smaller of two ceilings is a ceiling. Taking
--     the floor would compare a best case against a worst case.
--   * the NORMALLY AVAILABLE band (a4a_nordown) rather than the maximum one, because EETT
--     collects both and the first is closer to what somebody experiences. It is filed in
--     exactly the rows the maximum is, is never higher than it anywhere, and sits about a
--     third of a band below it on copper. Migration 0055 has the measurements; the short of
--     it is that the streets we can identify as being on 10 Mbps or less nearly doubles,
--     from 2,137 to 3,994, and every street it moves moves down.
--     coalesce back to maxdown anyway, so a future filing that carries one and not the
--     other is capped rather than uncapped.
--
-- least() ignores nulls, which is the behaviour that quietly invented 24 Mbps out of nothing
-- in 130 and is exactly right here: no band filed, and the open-ended ">= 1000" band whose
-- ceiling is null, both mean "nothing caps this" and both leave sold_mbps standing. 70.8% of
-- the million fibre filings carry no band and the rest are all ">= 1000", so fibre is never
-- capped by anything.
--
-- The maximum over every way this operator reaches the street, rather than its best line's
-- figure. Where a filing caps one technology below another — vectoring held to 10 while the
-- same operator's VDSL stands at 50 — the reader can have the 50, and answering with the
-- better line's worse number understates what is actually for sale.
insert into street_provider (street_id, provider_id, mbps)
select reached.street_id, reached.provider_id, max(reached.mbps)
from (
    select s.id as street_id, ac.provider_id, least(t.sold_mbps, coalesce(nb.max_mbps, sb.max_mbps)) as mbps
    from street s
    join address a
      on a.municipality_id = s.municipality_id and a.street_fold = s.name_fold
    join address_coverage ac on ac.address_id = a.id
    join technology t on t.code = ac.technology
    left join speed_band sb on sb.id = ac.speed_band_id
    left join speed_band nb on nb.id = ac.normal_band_id
    where ac.family <> 'wireless'

    union all

    -- Cabinet-sized areas only. Half the filed areas are under four hectares and are about
    -- the roads in them; a few hundred are tens of square kilometres and are about a
    -- district. Λίμνης Κορώνειας has no door on it and crosses nothing but three filings of
    -- 36.8 km2 — it was drawn at 100 and reported as nothing at all, along with 3,188
    -- others. The cap is cabinet_m2(), which api/main.py asks for by the same name rather
    -- than carrying its own copy.
    select s.id, ca.provider_id, least(t.sold_mbps, coalesce(nb.max_mbps, sb.max_mbps))
    from street s
    join coverage_area ca on st_intersects(ca.geom_2d, s.geom::geometry)
    join technology t on t.code = ca.technology
    left join speed_band sb on sb.id = ca.speed_band_id
    left join speed_band nb on nb.id = ca.normal_band_id
    where ca.family <> 'wireless'
      and ca.area_m2 <= cabinet_m2()
) reached
group by reached.street_id, reached.provider_id;
