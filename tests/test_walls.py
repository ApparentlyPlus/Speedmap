from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from probe.walls import BlockedError, refuse, wall

IMPERVA = (Path(__file__).parent / "fixtures" / "imperva_block.html").read_text()  # Vodafone's, scrubbed


def _page(body: str, status: int = 200, **headers: str) -> httpx.Response:
    return httpx.Response(status, headers={"content-type": "text/html", **headers}, text=body)


def test_wall() -> None:
    assert wall(_page(IMPERVA)) == "Imperva"
    # Telekom's eligibility page has the script on every load
    body = '<html><head><script src="/_Incapsula_Resource?SWJIYLWA=719d"></script></head><body>' + "x" * 9000
    assert wall(_page(body)) is None

    assert wall(_page("<title>Just a moment...</title>", 403, server="cloudflare")) == "Cloudflare"
    assert wall(_page("", 403, **{"cf-mitigated": "challenge"})) == "Cloudflare"
    # so do Nova's normal pages
    body = '<script src="/cdn-cgi/challenge-platform/scripts/jsd/main.js"></script>'
    assert wall(_page(body, 200, server="cloudflare")) is None

    assert wall(httpx.Response(429)) == "a rate limit"
    assert wall(httpx.Response(200, json={"available": True})) is None


def test_refuse() -> None:
    with pytest.raises(BlockedError, match="Imperva") as raised:
        refuse(_page(IMPERVA))
    assert raised.value.wall == "Imperva"
