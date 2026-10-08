"""Telling an operator's answer from its bot protection's."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from probe.walls import BlockedError, refuse, wall

FIXTURES = Path(__file__).parent / "fixtures"


def page(body: str, status: int = 200, **headers: str) -> httpx.Response:
    return httpx.Response(status, headers={"content-type": "text/html", **headers}, text=body)


def test_imperva_block_page_is_a_block() -> None:
    """Vodafone's, as it came back to a plain request, scrubbed of the requester's address."""
    assert wall(page((FIXTURES / "imperva_block.html").read_text())) == "Imperva"


def test_a_page_imperva_only_injects_a_script_into_is_not_a_block() -> None:
    """Telekom's real eligibility page carries the resource script on every load."""
    body = '<html><head><script src="/_Incapsula_Resource?SWJIYLWA=719d"></script></head><body>' + "x" * 9000
    assert wall(page(body)) is None


def test_cloudflare_challenge_is_a_block() -> None:
    assert wall(page("<title>Just a moment...</title>", 403, server="cloudflare")) == "Cloudflare"
    assert wall(page("", 403, **{"cf-mitigated": "challenge"})) == "Cloudflare"


def test_a_page_cloudflare_only_watches_is_not_a_block() -> None:
    """Nova's real pages load Cloudflare's challenge-platform script and answer 200."""
    body = '<script src="/cdn-cgi/challenge-platform/scripts/jsd/main.js"></script>'
    assert wall(page(body, 200, server="cloudflare")) is None


def test_a_rate_limit_is_a_block_whoever_sends_it() -> None:
    assert wall(httpx.Response(429)) == "a rate limit"


def test_an_answer_is_not_a_block() -> None:
    assert wall(httpx.Response(200, json={"available": True})) is None


def test_the_hook_raises_before_anything_parses_the_page() -> None:
    with pytest.raises(BlockedError, match="Imperva") as raised:
        refuse(page((FIXTURES / "imperva_block.html").read_text()))
    assert raised.value.wall == "Imperva"
