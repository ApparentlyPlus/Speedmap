from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from probe.ttl import CHANGING, FAILED, LIKELY, SETTLED, VOLATILE, ttl


def test_ttl() -> None:
    assert ttl(Decimal(1000)) == SETTLED
    assert ttl(Decimal(3000)) == SETTLED
    assert ttl(Decimal(500)) == LIKELY
    assert ttl(Decimal(300)) == LIKELY
    assert ttl(Decimal(299)) == CHANGING
    assert ttl(Decimal(100)) == CHANGING
    assert ttl(Decimal(99)) == VOLATILE
    assert ttl(Decimal(24)) == VOLATILE
    assert ttl(Decimal(24)) < ttl(Decimal(1000))


def test_ttl_no() -> None:
    assert ttl(None, serviceable=False) == VOLATILE
    assert ttl(Decimal(1000), serviceable=False) == VOLATILE
    # serviceable but no figure
    assert ttl(None) == VOLATILE

    assert timedelta(days=1) > FAILED
    assert min(SETTLED, LIKELY, CHANGING, VOLATILE) > FAILED
