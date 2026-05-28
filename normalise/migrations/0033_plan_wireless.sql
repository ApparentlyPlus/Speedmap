-- Fixed wireless is sold as a home broadband plan, not a mobile one, and the technology
-- vocabulary has said so since the schema was written. The plan table disagreed and would
-- have forced a 5G home router to be filed as mobile.
alter table plan drop constraint plan_family_check;

alter table plan add constraint plan_family_check
    check (family in ('fibre', 'coax', 'copper', 'wireless', 'satellite'));
