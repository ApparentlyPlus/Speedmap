"""Push alerts to a phone over ntfy. Without SPEEDMAP_NTFY_URL they're only logged."""

from __future__ import annotations

import logging
import threading

import httpx

from db.settings import settings

log = logging.getLogger("speedmap.alert")

TIMEOUT_S = 5.0


def alert(title: str, message: str, *, urgent: bool = False) -> bool:
    log.warning("alert: %s: %s", title, message)
    if not settings.ntfy_url:
        return False
    headers = {"Title": title.encode("utf-8").decode("latin-1", "replace"), "Tags": "speedmap"}
    if urgent:
        headers["Priority"] = "high"
    # undeliverable alerts get logged and dropped, the caller has its own work to finish
    try:
        r = httpx.post(settings.ntfy_url, content=message.encode("utf-8"), headers=headers, timeout=TIMEOUT_S)
    except httpx.HTTPError as e:
        log.error("alert not delivered: %s", e)
        return False
    if r.status_code >= 300:
        log.error("alert not delivered: ntfy answered %s", r.status_code)
        return False
    return True


def alert_later(title: str, message: str, *, urgent: bool = False) -> None:
    # not a daemon, so a job that's about to exit still sends it
    threading.Thread(target=alert, args=(title, message), kwargs={"urgent": urgent}).start()
