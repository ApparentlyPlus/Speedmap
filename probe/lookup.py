"""Gather what the decision needs, for one address and each provider that could serve it.

The street is the unit of evidence.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import psycopg
from psycopg.rows import TupleRow

from probe.decide import Answer, verdict

# The one provider whose checker was walked street by street. Only its silence below a
# ceiling counts as a refusal. Nobody else was ever asked.
SCANNED_BY = "TELEKOM"

INPUTS = """
with here as (
    select id, municipality_id, street_fold, street_id, checked_to,
           case when street_no ~ '^[0-9]+$' then street_no::int end as street_no
    from address where id = %(address_id)s
),
-- Whose presence on a street lets a seller offer it: its own, plus every network it resells
-- over. A seller with no wholesale deal reaches only itself.
reach as (
    select id as seller_id, id as infra_id from provider
    union
    select seller_id, infra_id from wholesale
),
-- Doors on this street by 065's pin, so fiber on a same-named road across town isn't
-- evidence here. By name only when there's no pin.
neighbours as (
    select a.id from address a, here h
    where h.street_id is not null and a.street_id = h.street_id
    union all
    select a.id from address a, here h
    where h.street_id is null
      and a.municipality_id = h.municipality_id and a.street_fold = h.street_fold
),
filed as (
    select ac.provider_id as infra_id, bool_or(ac.family = 'fiber') as fiber
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
       last.serviceable is false,
       h.street_no,
       case when p.code = %(scanned_by)s then h.checked_to end,
       coalesce(bool_or(filed.fiber), false),
       max(asked.best)
from provider p
cross join here h
left join lateral (
    select bool_or(v.serviceable) as serviceable, max(v.expires_at) as expires_at
    from availability v where v.address_id = h.id and v.provider_id = p.id
) ans on true
-- What they last said when asked. availability can't record a refusal, since it holds
-- offers and a refusal has none.
left join lateral (
    select a.serviceable
    from probe_attempt a
    where a.address_id = h.id and a.provider_id = p.id and a.ok
    order by a.attempted_at desc
    limit 1
) last on true
left join reach r on r.seller_id = p.id
left join filed on filed.infra_id = r.infra_id
left join asked on asked.infra_id = r.infra_id
where p.code = any(%(providers)s)
group by p.code, ans.serviceable, ans.expires_at, last.serviceable, h.street_no, h.checked_to
order by p.code
"""


def verdicts(
    conn: psycopg.Connection[TupleRow],
    address_id: int,
    providers: list[str],
    *,
    now: datetime,
) -> dict[str, str]:
    """What each provider's answer for this address rests on, and whether to ask them."""
    rows = conn.execute(
        INPUTS,
        {"address_id": address_id, "providers": providers, "scanned_by": SCANNED_BY},
    ).fetchall()

    verdicts: dict[str, str] = {}
    for code, serviceable, expires_at, refused, street_no, checked_to, fiber, best in rows:
        answer = Answer(serviceable=serviceable, expires_at=expires_at) if expires_at is not None else None
        verdicts[str(code)] = verdict(
            answer,
            now=now,
            street_no=street_no,
            checked_to=checked_to,
            street_best_mbps=Decimal(best) if best is not None else None,
            street_fiber=bool(fiber),
            refused=bool(refused),
        )
    return verdicts
