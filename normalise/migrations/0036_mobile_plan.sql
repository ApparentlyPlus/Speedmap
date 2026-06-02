-- A data plan bought to feed a router is not fixed wireless: the operator sells airtime and
-- nothing else, so the router is the customer's problem and the coverage is the mobile grid
-- rather than the fixed one. It is the fallback when no line reaches an address, and it has
-- to be nameable to be compared against the plans that do.
insert into technology (code, family) values ('MOBILE', 'wireless');
