-- The scrape walked house numbers upward from the start of each street and stopped after
-- five consecutive numbers with no service, so a street is known only up to a ceiling:
-- the median street was scanned to number 14. Below it a missing number means the operator
-- was asked and said no. Above it nothing was ever asked, and only a live check can say.
-- Without this the two look identical and the addresses most likely to need asking are the
-- ones we would skip.
create table cosmote_scan (
    municipality_id int not null references municipality (id),
    street_fold text not null,
    scanned_to int not null,
    primary key (municipality_id, street_fold)
);
