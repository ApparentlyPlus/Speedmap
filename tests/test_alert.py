"""Alerts to the owner's phone."""

from __future__ import annotations

import httpx
import pytest

from alert import alert
from db.settings import settings


def test_with_no_topic_set_nothing_is_sent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "ntfy_url", None)
    monkeypatch.setattr(httpx, "post", lambda *a, **k: pytest.fail("sent with no topic"))
    assert alert("canary failed", "TELEKOM") is False


def test_an_alert_goes_to_the_topic_with_its_title(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    def post(url: str, content: bytes, headers: dict[str, str], timeout: float) -> httpx.Response:
        seen.update(url=url, body=content.decode(), title=headers["Title"], priority=headers.get("Priority"))
        return httpx.Response(200)

    monkeypatch.setattr(settings, "ntfy_url", "https://ntfy.example/speedmap-topic")
    monkeypatch.setattr(httpx, "post", post)
    assert alert("TELEKOM is blocking us", "resting", urgent=True) is True
    assert seen == {
        "url": "https://ntfy.example/speedmap-topic", "body": "resting",
        "title": "TELEKOM is blocking us", "priority": "high",
    }


def test_a_notifier_that_is_down_never_breaks_the_caller(monkeypatch: pytest.MonkeyPatch) -> None:
    def down(*args: object, **kwargs: object) -> httpx.Response:
        raise httpx.ConnectError("no route")

    monkeypatch.setattr(settings, "ntfy_url", "https://ntfy.example/speedmap-topic")
    monkeypatch.setattr(httpx, "post", down)
    assert alert("x", "y") is False
