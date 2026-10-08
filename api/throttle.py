"""How often one caller may ask, per kind of request.

Caddy can't rate-limit without a plugin it doesn't ship with, so it happens here. The Pi runs
one API process, so a counter in memory is the whole picture, and a restart forgetting it is
harmless: the limits are about a minute or an hour, not a day.

Live checks are the one that matters. Each asks an operator on our behalf, and a loop of them
from one visitor is how an operator would decide we're the bot. The rest are generous enough
that only a script would meet them.
"""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from fastapi import Request, Response
from fastapi.responses import JSONResponse


@dataclass(frozen=True)
class Limit:
    name: str
    times: int
    per_s: int


# A reader opening an address sets off a live check per operator, three at most, so this is
# about ten addresses in ten minutes.
PROBE = Limit("probe", 30, 600)
ASK = Limit("ask", 20, 3600)  # addresses made because someone typed a number we didn't have
REPORT = Limit("report", 5, 3600)
SEARCH = Limit("search", 240, 60)  # a keystroke each, after the debounce
READ = Limit("read", 600, 60)


def limit_for(method: str, path: str) -> Limit:
    if method == "POST" and path.endswith("/probe"):
        return PROBE
    if method == "POST" and path.endswith("/addresses"):
        return ASK
    if method == "POST" and path.startswith("/reports"):
        return REPORT
    if path.startswith("/search"):
        return SEARCH
    return READ


class Throttle:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self.clock = clock
        self.seen: dict[tuple[str, str], deque[float]] = {}
        self.swept = clock()

    def wait(self, caller: str, limit: Limit) -> int:
        """Seconds until this caller may ask again, 0 when they may now. Counts the ask."""
        now = self.clock()
        if now - self.swept > 300:
            self.sweep(now)
        stamps = self.seen.setdefault((caller, limit.name), deque())
        while stamps and stamps[0] <= now - limit.per_s:
            stamps.popleft()
        if len(stamps) >= limit.times:
            return max(1, int(stamps[0] + limit.per_s - now) + 1)
        stamps.append(now)
        return 0

    def sweep(self, now: float) -> None:
        """Forget callers with nothing left in their window, so the table can't only grow."""
        longest = max(one.per_s for one in (PROBE, ASK, REPORT, SEARCH, READ))
        self.seen = {key: s for key, s in self.seen.items() if s and s[-1] > now - longest}
        self.swept = now


throttle = Throttle()


async def throttled(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    """Middleware. The caller is the address Caddy forwarded for, which uvicorn's
    --proxy-headers puts in request.client."""
    caller = request.client.host if request.client is not None else "unknown"
    wait = throttle.wait(caller, limit_for(request.method, request.url.path))
    if wait:
        return JSONResponse(
            {"detail": "too many requests, try again shortly"}, status_code=429,
            headers={"Retry-After": str(wait)},
        )
    return await call_next(request)
