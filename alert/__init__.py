"""Telling the owner something needs looking at, by ntfy push to a phone.

The Pi runs alone. A canary failing at 02:00, an operator blocking us, a rebuild that didn't
finish: each used to be a line in a journal nobody reads. With SPEEDMAP_NTFY_URL set (an ntfy
topic, e.g. https://ntfy.sh/<something long and unguessable>) they arrive as notifications.
Unset, nothing is sent and the alert is only logged, which is what development and tests want.

An alert that can't be delivered is logged and dropped. Whatever raised it has its own work
to finish, and a broken notifier mustn't break that too.
"""

from __future__ import annotations

import logging
import threading

import httpx

from db.settings import settings

log = logging.getLogger("speedmap.alert")

# long enough for a slow link, short enough that a request waiting on it doesn't stall
TIMEOUT_S = 5.0


def alert(title: str, message: str, *, urgent: bool = False) -> bool:
    """Send one notification. True when it was delivered."""
    log.warning("alert: %s: %s", title, message)
    if not settings.ntfy_url:
        return False
    headers = {"Title": title.encode("utf-8").decode("latin-1", "replace"), "Tags": "speedmap"}
    if urgent:
        headers["Priority"] = "high"
    try:
        response = httpx.post(settings.ntfy_url, content=message.encode("utf-8"), headers=headers, timeout=TIMEOUT_S)
    except httpx.HTTPError as error:
        log.error("alert not delivered: %s", error)
        return False
    if response.status_code >= 300:
        log.error("alert not delivered: ntfy answered %s", response.status_code)
        return False
    return True


def alert_later(title: str, message: str, *, urgent: bool = False) -> None:
    """The same, off the request's thread: a reader shouldn't wait on our phone.

    Not a daemon, so a job that's about to exit still sends it first.
    """
    threading.Thread(target=alert, args=(title, message), kwargs={"urgent": urgent}).start()
