"""Telling a block from an answer.

Telekom and Vodafone sit behind Imperva, Nova behind Cloudflare. When either decides we're a
bot it doesn't fail the request, it answers with its own page instead, often with a 200. Read
as an answer, that was a parse error, counted against one address, and the next address asked
the same operator straight away: the way a short block becomes a long one.

Both vendors also put their scripts into ordinary pages. Telekom's eligibility page carries
_Incapsula_Resource and Nova's carries challenge-platform, so neither marker alone means a
block. Only the block pages' own furniture counts.
"""

from __future__ import annotations

import httpx

from probe.adapter import ProbeError

# Imperva's block page names its incident, and frames its resource in a page of nothing else.
IMPERVA = ("Incapsula incident ID", "Request unsuccessful. Incapsula")
IMPERVA_FRAME = ('id="main-iframe"', "_Incapsula_Resource")

# Cloudflare's interstitials, which come with a 403 or a 503
CLOUDFLARE = ("Just a moment...", "Attention Required! | Cloudflare", 'id="cf-error-details"')

# A block page is a few kilobytes. Reading further into a real page proves nothing.
SNIFF = 8000


class BlockedError(ProbeError):
    """The operator's bot protection answered instead of the operator."""

    def __init__(self, wall: str) -> None:
        super().__init__(f"blocked by {wall}")
        self.wall = wall


def wall(response: httpx.Response) -> str | None:
    """Whose block this response is, or None when it's the operator talking."""
    if response.status_code == httpx.codes.TOO_MANY_REQUESTS:
        return "a rate limit"
    headers = response.headers
    if headers.get("cf-mitigated", "").lower() == "challenge":
        return "Cloudflare"
    if "html" not in headers.get("content-type", ""):
        return None

    page = response.text[:SNIFF]
    if any(mark in page for mark in IMPERVA) or all(mark in page for mark in IMPERVA_FRAME):
        return "Imperva"
    cloudflare = "cloudflare" in headers.get("server", "").lower()
    if cloudflare and response.status_code in (403, 503) and any(mark in page for mark in CLOUDFLARE):
        return "Cloudflare"
    return None


def refuse(response: httpx.Response) -> None:
    """An httpx response hook: raise on a block, before anything tries to parse it."""
    response.read()
    found = wall(response)
    if found is not None:
        raise BlockedError(found)
