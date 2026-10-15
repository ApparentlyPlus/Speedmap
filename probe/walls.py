"""Spot a bot wall's page, often sent with a 200. Imperva for Telekom and Vodafone, Cloudflare for Nova."""

from __future__ import annotations

import httpx

from probe.adapter import ProbeError

# their scripts sit in normal pages too, so only block page markers count
IMPERVA = ("Incapsula incident ID", "Request unsuccessful. Incapsula")
IMPERVA_FRAME = ('id="main-iframe"', "_Incapsula_Resource")  # both, or it's a normal page

# with a 403 or 503
CLOUDFLARE = ("Just a moment...", "Attention Required! | Cloudflare", 'id="cf-error-details"')

SNIFF = 8000  # block pages are a few KB


class BlockedError(ProbeError):
    def __init__(self, wall: str) -> None:
        super().__init__(f"blocked by {wall}")
        self.wall = wall


def wall(response: httpx.Response) -> str | None:
    if response.status_code == httpx.codes.TOO_MANY_REQUESTS:
        return "a rate limit"
    headers = response.headers
    if headers.get("cf-mitigated", "").lower() == "challenge":
        return "Cloudflare"
    if "html" not in headers.get("content-type", ""):
        return None

    page = response.text[:SNIFF]
    if any(m in page for m in IMPERVA) or all(m in page for m in IMPERVA_FRAME):
        return "Imperva"
    cf = "cloudflare" in headers.get("server", "").lower()
    if cf and response.status_code in (403, 503) and any(m in page for m in CLOUDFLARE):
        return "Cloudflare"
    return None


def refuse(response: httpx.Response) -> None:
    # httpx response hook, runs before anything parses the body
    response.read()
    w = wall(response)
    if w is not None:
        raise BlockedError(w)
