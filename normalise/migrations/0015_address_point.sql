-- Which infrastructure points an address was built from. One address usually has more than
-- one: 404,423 addresses are filed by two different builders and 3,279 by three, each with
-- its own coverid. coverid is what coverage.source_ref holds, so this is the join that
-- answers what is available at an address.
create table address_point (
    address_id bigint not null references address (id) on delete cascade,
    coverid text not null,
    primary key (address_id, coverid)
);

create index on address_point (coverid);
