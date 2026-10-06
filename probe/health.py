"""How each operator's checker is doing.

Leaving an operator out of a comparison is a worse lie than showing the gap: the reader
can't tell "we asked and they said no" from "we couldn't ask".
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import psycopg
from psycopg.rows import TupleRow

HEALTHY = "healthy"
DEGRADED = "degraded"
BROKEN = "broken"
UNTRIED = "untried"

# How far back an answer still shows the checker works. Longer than the nightly canary, so
# one missed run doesn't raise an alarm.
WINDOW = timedelta(days=3)

# Below this success rate something's wrong even with answers arriving. One in three isn't
# working.
SHAKY = 0.8

# Askable attempts only. Both parts read (provider_id, attempted_at desc): the window as a
# range, the last success by walking back from the newest. It used to aggregate every
# attempt ever, on a table the sweep grows by hundreds of rows a night.
SINCE = """
select p.code, coalesce(recent.n, 0), coalesce(recent.ok, 0), last.at
from provider p
left join lateral (
    select count(*) filter (where a.askable) as n,
           count(*) filter (where a.askable and a.ok) as ok
    from probe_attempt a
    where a.provider_id = p.id and a.attempted_at >= %(since)s
) recent on true
left join lateral (
    select a.attempted_at as at
    from probe_attempt a
    where a.provider_id = p.id and a.ok
    order by a.attempted_at desc
    limit 1
) last on true
where p.code = any(%(codes)s)
"""


@dataclass(frozen=True)
class Health:
    provider: str
    state: str
    last_ok_at: datetime | None
    attempts: int
    answered: int

    @property
    def says(self) -> str:
        """What to tell the reader, in their terms."""
        if self.state == HEALTHY:
            return "answering"
        if self.state == UNTRIED:
            # untried covers two silences that shouldn't read alike: never asked, and not
            # asked lately
            if self.last_ok_at is None:
                return "not asked yet"
            return f"last answered {self.last_ok_at:%-d %B}"
        if self.state == DEGRADED:
            # degraded means it is answering, just not every time (state only gets here when
            # answered > 0)
            return f"answering {self.answered} times in {self.attempts}"
        if self.last_ok_at is None:
            return "has never answered"
        return f"has not answered since {self.last_ok_at:%-d %B}"


def state(recent: int, answered: int, last_ok: datetime | None, now: datetime) -> str:
    """Healthy, shaky or gone."""
    if recent == 0:
        # Nothing asked lately. Fine if it answered within the window, the sweep may just
        # have had nothing due.
        return HEALTHY if last_ok is not None and now - last_ok <= WINDOW else UNTRIED
    if answered == 0:
        return BROKEN
    return HEALTHY if answered / recent >= SHAKY else DEGRADED


def health(
    conn: psycopg.Connection[TupleRow], codes: list[str], now: datetime
) -> dict[str, Health]:
    """One state per operator, worked out from what happened. No stored flag."""
    rows = conn.execute(
        SINCE, {"since": now - WINDOW, "codes": codes}
    ).fetchall()
    states: dict[str, Health] = {}
    for code, recent, answered, last_ok in rows:
        states[str(code)] = Health(
            provider=str(code),
            state=state(int(recent), int(answered), last_ok, now),
            last_ok_at=last_ok,
            attempts=int(recent),
            answered=int(answered),
        )
    return states
