-- What a customer would recognise, which is not always what the register calls them.
--
-- The register files the corporate entity: OTE is the incumbent's legal name and nobody
-- shops for it. The shop, the bills and the router all say Telekom, and a comparison that
-- names the holding company is asking the reader to do a translation we already know.
-- The code stays OTE, because that is what the register keys on and what every join uses.
update provider set display_name = 'Telekom' where code = 'OTE';
update provider set display_name = 'ΔΕΗ Fiber' where code = 'DEI';
update provider set display_name = 'Inalan' where code = 'INALAN';
