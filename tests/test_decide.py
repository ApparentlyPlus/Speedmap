from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from probe.decide import ASK, FRESH, INFERRED, REFUSED, STALE, UNKNOWN, Answer, verdict

NOW = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)


def _answer(days: int, *, serviceable: bool = True) -> Answer:
    return Answer(serviceable=serviceable, expires_at=NOW + timedelta(days=days))


def test_verdict_expiry() -> None:
    assert verdict(_answer(30), now=NOW) == FRESH
    assert verdict(_answer(-1), now=NOW) == STALE
    assert verdict(_answer(0), now=NOW) == STALE
    # a no is an answer too
    assert verdict(_answer(30, serviceable=False), now=NOW) == FRESH


def test_verdict_scan() -> None:
    assert verdict(None, now=NOW, street_no=7, checked_to=14) == REFUSED
    assert verdict(None, now=NOW, street_no=14, checked_to=14) == REFUSED
    # Τζελίλη 40 is served, the scan stopped at 1
    assert verdict(None, now=NOW, street_no=40, checked_to=1) == UNKNOWN
    assert verdict(None, now=NOW, street_no=7, checked_to=None) == UNKNOWN
    assert verdict(None, now=NOW, street_no=None, checked_to=14) == UNKNOWN


def test_ask() -> None:
    assert {STALE, REFUSED, UNKNOWN} == ASK
    assert FRESH not in ASK
    assert INFERRED not in ASK


def test_verdict_street() -> None:
    assert verdict(None, now=NOW, street_best_mbps=Decimal(1000)) == INFERRED
    assert verdict(None, now=NOW, street_best_mbps=Decimal(3000)) == INFERRED
    # copper depends on the cabinet
    assert verdict(None, now=NOW, street_best_mbps=Decimal(500)) == UNKNOWN
    assert verdict(None, now=NOW, street_best_mbps=Decimal(100)) == UNKNOWN

    assert verdict(_answer(30), now=NOW, street_best_mbps=Decimal(1000)) == FRESH
    assert verdict(_answer(-1), now=NOW, street_best_mbps=Decimal(1000)) == INFERRED
    assert verdict(None, now=NOW, street_no=7, checked_to=14, street_best_mbps=Decimal(1000)) == INFERRED

    # 712,026 fiber rows have no band at all
    assert verdict(None, now=NOW, street_fiber=True) == INFERRED
    assert verdict(None, now=NOW, street_fiber=True, street_best_mbps=None) == INFERRED
    assert verdict(None, now=NOW, street_fiber=False, street_best_mbps=Decimal(100)) == UNKNOWN


def test_verdict_refused() -> None:
    assert verdict(None, now=NOW, refused=True) == REFUSED
    assert verdict(None, now=NOW, refused=False) == UNKNOWN
    assert verdict(None, now=NOW, refused=True, street_fiber=True) == INFERRED
