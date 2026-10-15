"""How each operator's checker is doing, so a reader can tell "they said no" from "we couldn't ask"."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import psycopg
from psycopg.rows import TupleRow

from probe.run import STREAK, resting

HEALTHY = "healthy"
DEGRADED = "degraded"
BROKEN = "broken"
UNTRIED = "untried"
BLOCKED = "blocked"  # resting behind a bot wall, readers get the cache

# longer than the nightly canary so one missed run isn't an alarm
WINDOW = timedelta(days=3)

SHAKY = 0.8

# askable attempts only, both halves use the (provider_id, attempted_at desc) index
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
    # set while BLOCKED
    blocked_by: str | None = None
    resting_until: datetime | None = None

    @property
    def says(self) -> str:
        if self.state == BLOCKED and self.resting_until is not None:
            # postgres hands back its own zone
            return f"blocked by {self.blocked_by}, asked again after {self.resting_until.astimezone(UTC):%H:%M} UTC"
        if self.state == HEALTHY:
            return "answering"
        if self.state == UNTRIED:
            if self.last_ok_at is None:
                return "not asked yet"
            return f"last answered {self.last_ok_at:%-d %B}"
        if self.state == DEGRADED:
            return f"answering {self.answered} times in {self.attempts}"
        if self.last_ok_at is None:
            return "has never answered"
        return f"has not answered since {self.last_ok_at:%-d %B}"


def state(recent: int, answered: int, last_ok: datetime | None, now: datetime) -> str:
    if recent == 0:
        # the sweep may just have had nothing due
        return HEALTHY if last_ok is not None and now - last_ok <= WINDOW else UNTRIED
    if answered == 0:
        return BROKEN
    return HEALTHY if answered / recent >= SHAKY else DEGRADED


def health(conn: psycopg.Connection[TupleRow], codes: list[str], now: datetime) -> dict[str, Health]:
    rows = conn.execute(SINCE, {"since": now - WINDOW, "codes": codes}).fetchall()
    states: dict[str, Health] = {}
    for code, recent, answered, last_ok in rows:
        until = resting(conn, str(code), now)
        wall = None
        if until is not None:
            hit = conn.execute(STREAK, {"code": str(code)}).fetchone()
            wall = None if hit is None else hit[0]
        states[str(code)] = Health(
            provider=str(code),
            state=BLOCKED if until is not None else state(int(recent), int(answered), last_ok, now),
            last_ok_at=last_ok,
            attempts=int(recent),
            answered=int(answered),
            blocked_by=wall,
            resting_until=until,
        )
    return states
