-- What each kind of line is actually sold at, which is now what the map is painted by.
--
-- The register's own speeds are no longer consulted for the figure. They are classes, most
-- of them are absent — 70.8% of the 1,071,133 FTTH filings carry no band at all — and where
-- they are present they are filed at speeds the line cannot carry: ADSL at 100-300 and at
-- >= 1000. Anchoring on the technology instead is a decision taken deliberately and with
-- the risk understood: the line that runs down a street is a fact about the street, and how
-- fast that kind of line goes is a fact about the country.
--
-- The numbers are not max_plausible_mbps, which is a physics ceiling nobody sells. They are
-- what operators actually retail on each line, taken from the scraped plans in this
-- database:
--
--   ADSL       24    the one ADSL plan on file (Vodafone)
--   VDSL       50    every VDSL plan: OTE 50, Vodafone 50. Not 100 — nobody sells 100.
--   VECT_VDSL  100   every vectored plan: OTE, Vodafone and Nova, all three at exactly 100.
--                    Not 300: 300 is what vectoring can do, not what anyone will sell you.
--   FTTH       1000  plans run 100 to 3000; a gigabit is the common tier and the register's
--                    own top band is open-ended at 1000, so no street can be known quicker.
--   DOCSIS     300   Greece files no coax at all — zero rows in coverage and coverage_area —
--                    so this colours nothing today. It is set rather than left null so that
--                    a cable filing, if one ever arrives, reports a figure instead of
--                    vanishing.
--
-- Wireless keeps a figure too, for the address panel rather than for the map: the street map
-- leaves mobile out entirely, because 5G reaches nearly every address and a map of it is a
-- map of Greece in one colour.
--
-- max_plausible_mbps stays where it is. It is what the line could carry and this is what it
-- is sold at, and the two are different questions; the ranker still asks the first.
alter table technology add sold_mbps numeric;

comment on column technology.sold_mbps is
    'What this kind of line is retailed at, from the scraped plans. The map paints this.';

update technology set sold_mbps = v.mbps from (values
    ('ADSL', 24), ('VDSL', 50), ('VECT_VDSL', 100), ('DOCSIS', 300), ('FTTH', 1000),
    ('FWA_4G', 50), ('FWA_5G', 300), ('SAT', 100)
) as v (code, mbps) where technology.code = v.code;
