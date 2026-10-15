"""Per caller rate limits. In memory is fine, the Pi runs one API process."""

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


PROBE = Limit("probe", 30, 600)  # the one that matters, ~10 addresses in 10 minutes
ASK = Limit("ask", 20, 3600)
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
        """Seconds to wait, 0 if they may ask now (which counts)."""
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
        longest = max(x.per_s for x in (PROBE, ASK, REPORT, SEARCH, READ))
        self.seen = {key: s for key, s in self.seen.items() if s and s[-1] > now - longest}
        self.swept = now


throttle = Throttle()


async def throttled(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    # uvicorn --proxy-headers puts Caddy's forwarded address in request.client
    caller = request.client.host if request.client is not None else "unknown"
    wait = throttle.wait(caller, limit_for(request.method, request.url.path))
    if wait:
        return JSONResponse(
            {"detail": "too many requests, try again shortly"}, status_code=429,
            headers={"Retry-After": str(wait)},
        )
    return await call_next(request)
