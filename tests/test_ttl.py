"""How long an answer is worth keeping."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from probe.ttl import CHANGING, FAILED, LIKELY, SETTLED, VOLATILE, ttl


def test_a_gigabit_address_is_settled() -> None:
    """Fiber is not dug up again. Only a new operator arriving changes what is true there."""
    assert ttl(Decimal(1000)) == SETTLED
    assert ttl(Decimal(3000)) == SETTLED


def test_the_bands_step_down_with_the_speed() -> None:
    assert ttl(Decimal(500)) == LIKELY
    assert ttl(Decimal(300)) == LIKELY
    assert ttl(Decimal(299)) == CHANGING
    assert ttl(Decimal(100)) == CHANGING
    assert ttl(Decimal(99)) == VOLATILE


def test_a_slow_address_is_the_least_stable_thing_on_the_map() -> None:
    """It is precisely where someone is building, so it is asked again soonest."""
    assert ttl(Decimal(24)) == VOLATILE
    assert ttl(Decimal(24)) < ttl(Decimal(1000))


def test_no_service_is_rechecked_as_often_as_the_slowest_line() -> None:
    """Absence is overturned by a single trench."""
    assert ttl(None, serviceable=False) == VOLATILE
    assert ttl(Decimal(1000), serviceable=False) == VOLATILE


def test_an_unquoted_speed_is_not_treated_as_settled() -> None:
    """Serviceable with no figure is an answer, but not one to keep for two years."""
    assert ttl(None) == VOLATILE


def test_a_failure_is_never_cached_as_a_fact() -> None:
    """It is retried in hours. Nothing else here is measured in hours."""
    assert timedelta(days=1) > FAILED
    assert min(SETTLED, LIKELY, CHANGING, VOLATILE) > FAILED
