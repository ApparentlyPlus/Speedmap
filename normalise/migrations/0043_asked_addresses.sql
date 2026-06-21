-- Addresses nobody filed, made because someone asked for one.
--
-- The register holds 1.8M addresses and the street layer holds the streets under them, and
-- the two do not agree: a street can be known while most of its numbers are not. The
-- register files nothing at all on some streets, and the Cosmote scrape walked away from
-- others after five consecutive numbers came back empty. Τζελίλη 40 is a front door in
-- both cases and is in neither source.
--
-- Given the street, the number can be made rather than refused. It is a source like the
-- other two because that is what it is: a place these rows came from, with its own answer
-- to who to believe when two sources disagree. The reader asked; nothing else vouches for
-- it; and any of it the register later files will collide on the address unique key and
-- stay one address rather than becoming two.
insert into source (name, url, licence) values (
    'asked',
    null,
    'Asked for by a reader, on a street the register or the street layer already holds'
) on conflict (name) do nothing;
