"""Gather what the decision needs, for one address, for each provider that could serve it.

The street is the unit of evidence. A seller inherits it from every network it resells over,
so what the operator's own checker learned about a street answers for its wholesale
customers too: the register knows OTE fibre on 2,901 streets and the scrape knows it on
50,757, and Nova sells over all of them.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import psycopg
from psycopg.rows import TupleRow

from probe.decide import Answer, verdict

# The one provider whose checker was walked street by street. Only its silence below a
# ceiling means a refusal; for everyone else nothing was ever asked.
SCANNED_BY = "OTE"

INPUTS = """
with here as (
    select id, municipality_id, street_fold, checked_to,
           case when street_no ~ '^[0-9]+$' then street_no::int end as street_no
    from address where id = %(address_id)s
),
-- Whose presence on a street lets a seller offer it: itself, and every network it resells
-- over. Sellers with no wholesale deal simply reach only themselves.
reach as (
    select id as seller_id, id as infra_id from provider
    union
    select seller_id, infra_id from wholesale
),
neighbours as (
    select a.id from address a, here h
    where a.municipality_id = h.municipality_id and a.street_fold = h.street_fold
),
filed as (
    select ac.provider_id as infra_id, bool_or(ac.family = 'fibre') as fibre
    from address_coverage ac join neighbours n on n.id = ac.address_id
    group by 1
),
asked as (
    select v.provider_id as infra_id, max(v.max_down_mbps) as best
    from availability v join neighbours n on n.id = v.address_id
    group by 1
)
select p.code,
       ans.serviceable, ans.expires_at,
       h.street_no,
       case when p.code = %(scanned_by)s then h.checked_to end,
       coalesce(bool_or(filed.fibre), false),
       max(asked.best)
from provider p
cross join here h
left join lateral (
    select bool_or(v.serviceable) as serviceable, max(v.expires_at) as expires_at
    from availability v where v.address_id = h.id and v.provider_id = p.id
) ans on true
left join reach r on r.seller_id = p.id
left join filed on filed.infra_id = r.infra_id
left join asked on asked.infra_id = r.infra_id
where p.code = any(%(providers)s)
group by p.code, ans.serviceable, ans.expires_at, h.street_no, h.checked_to
order by p.code
"""


def verdicts(
    conn: psycopg.Connection[TupleRow],
    address_id: int,
    providers: list[str],
    *,
    now: datetime,
) -> dict[str, str]:
    """What is known about this address from each provider, and whether to ask them."""
    rows = conn.execute(
        INPUTS,
        {"address_id": address_id, "providers": providers, "scanned_by": SCANNED_BY},
    ).fetchall()

    found: dict[str, str] = {}
    for code, serviceable, expires_at, street_no, checked_to, fibre, best in rows:
        answer = (
            Answer(serviceable=serviceable, expires_at=expires_at)
            if expires_at is not None
            else None
        )
        found[str(code)] = verdict(
            answer,
            now=now,
            street_no=street_no,
            checked_to=checked_to,
            street_best_mbps=Decimal(best) if best is not None else None,
            street_fibre=bool(fibre),
        )
    return found
