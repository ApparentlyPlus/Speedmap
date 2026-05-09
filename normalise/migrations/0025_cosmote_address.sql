-- The operator serves streets the register never filed: 168 of the 333 municipalities have
-- no register address at all. Those rows are a gazetteer of their own, not duplicates
-- waiting to happen, and search is the poorer for leaving them out.
insert into source (name, url, licence) values (
    'cosmote',
    'https://www.telekom.gr/eshop/jsp/eligibility.jsp',
    'Operator availability checker, public endpoint'
);

alter table address add source text not null default 'register' references source (name);

-- The cadastral parcel the operator resolved the address to. Nothing reads it yet, but it
-- identifies a building far more exactly than an interpolated point ever will.
alter table address add kaek text;
