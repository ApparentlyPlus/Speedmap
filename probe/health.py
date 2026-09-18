"""How each operator's checker is faring.

An operator missing from a comparison is a worse lie than a visible gap: the reader has no
way to tell "we asked and they said no" from "we could not ask". So the state is derived,
named, and meant to be shown — "Nova has not answered since 12 March" rather than silence.

Derived from attempts rather than stored, because a stored status is one more thing that can
be stale while the thing it describes has moved on.
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

# How far back an answer still counts as evidence the checker works. Longer than the
# nightly canary by enough that one missed run is not an alarm.
WINDOW = timedelta(days=3)

# Below this share of attempts succeeding, something is wrong even though answers are
# arriving: a checker that works one time in three is not working.
SHAKY = 0.8

# Askable attempts only. An address we hold no spelling for cannot be put to the operator at
# all, and counting that as the operator failing to answer reports the state of our own
# address book as the state of their checker — which it did: on 19 September every request
# OTE and Vodafone actually made succeeded, and both read as degraded. See migration 0057.
SINCE = """
select p.code,
       count(*) filter (where a.attempted_at >= %(since)s and a.askable) as recent,
       count(*) filter (where a.attempted_at >= %(since)s and a.askable and a.ok) as recent_ok,
       max(a.attempted_at) filter (where a.ok) as last_ok
from provider p
left join probe_attempt a on a.provider_id = p.id
where p.code = any(%(codes)s)
group by p.code
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
        """What the reader should be told, in the reader's terms."""
        if self.state == HEALTHY:
            return "answering"
        if self.state == UNTRIED:
            # Untried covers two different silences and they should not read alike: one we
            # have never put a question to, and one we have but not lately — which is what
            # an operator looks like when every recent address handed to it was one we hold
            # no spelling for.
            if self.last_ok_at is None:
                return "not asked yet"
            return f"last answered {self.last_ok_at:%-d %B}"
        if self.state == DEGRADED:
            # Degraded means it IS answering, just not every time — `state` only reaches it
            # when answered is above zero. Falling through to the sentence below said "has
            # not answered since 19 September" about an operator that had answered on the
            # 19th, which is the most recent day there was, and read to a reader as the
            # operator having no data at all rather than as a flaky checker.
            return f"answering {self.answered} times in {self.attempts}"
        if self.last_ok_at is None:
            return "has never answered"
        return f"has not answered since {self.last_ok_at:%-d %B}"


def state(recent: int, answered: int, last_ok: datetime | None, now: datetime) -> str:
    """Healthy, shaky, or gone."""
    if recent == 0:
        # Nothing asked lately. If it answered within the window it is fine; the sweep may
        # simply have had nothing due.
        return HEALTHY if last_ok is not None and now - last_ok <= WINDOW else UNTRIED
    if answered == 0:
        return BROKEN
    return HEALTHY if answered / recent >= SHAKY else DEGRADED


def health(
    conn: psycopg.Connection[TupleRow], codes: list[str], now: datetime
) -> dict[str, Health]:
    """One state per operator, derived from what happened rather than from a stored flag."""
    rows = conn.execute(
        SINCE, {"since": now - WINDOW, "codes": codes}
    ).fetchall()
    found: dict[str, Health] = {}
    for code, recent, answered, last_ok in rows:
        found[str(code)] = Health(
            provider=str(code),
            state=state(int(recent), int(answered), last_ok, now),
            last_ok_at=last_ok,
            attempts=int(recent),
            answered=int(answered),
        )
    return found
