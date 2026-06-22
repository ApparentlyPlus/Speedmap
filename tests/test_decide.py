"""Deciding whether an address still needs asking."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from probe.decide import ASK, FRESH, INFERRED, REFUSED, STALE, UNKNOWN, Answer, verdict

NOW = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)


def answer(days: int, *, serviceable: bool = True) -> Answer:
    return Answer(serviceable=serviceable, expires_at=NOW + timedelta(days=days))


def test_an_unexpired_answer_is_fresh() -> None:
    assert verdict(answer(30), now=NOW) == FRESH


def test_an_expired_answer_is_stale_not_absent() -> None:
    """A year-old answer is still evidence; it is shown while the check runs."""
    assert verdict(answer(-1), now=NOW) == STALE


def test_expiry_is_exclusive() -> None:
    assert verdict(answer(0), now=NOW) == STALE


def test_a_refusal_is_cached_as_an_answer() -> None:
    """The operator saying no is a result, and it expires like any other."""
    assert verdict(answer(30, serviceable=False), now=NOW) == FRESH


def test_a_number_within_the_scan_was_asked_and_refused() -> None:
    """The scan walked upward recording only what it found, so a gap below is a no."""
    assert verdict(None, now=NOW, street_no=7, checked_to=14) == REFUSED
    assert verdict(None, now=NOW, street_no=14, checked_to=14) == REFUSED


def test_a_number_above_the_scan_was_never_asked() -> None:
    """Τζελίλη 40 exists and is served; the scan stopped at 1."""
    assert verdict(None, now=NOW, street_no=40, checked_to=1) == UNKNOWN


def test_a_provider_that_never_scanned_refuses_nothing() -> None:
    """Only the operator that was walked may have its silence read as a refusal."""
    assert verdict(None, now=NOW, street_no=7, checked_to=None) == UNKNOWN


def test_an_address_with_no_number_is_never_refused() -> None:
    """A street without a number cannot be compared to a ceiling."""
    assert verdict(None, now=NOW, street_no=None, checked_to=14) == UNKNOWN


def test_everything_but_fresh_is_worth_asking() -> None:
    assert {STALE, REFUSED, UNKNOWN} == ASK
    assert FRESH not in ASK


def test_a_gigabit_street_needs_no_asking() -> None:
    """Fibre is dug street by street: a gigabit on this street is a gigabit at this door."""
    assert verdict(None, now=NOW, street_best_mbps=Decimal(1000)) == INFERRED
    assert verdict(None, now=NOW, street_best_mbps=Decimal(3000)) == INFERRED


def test_a_slower_street_is_still_asked() -> None:
    """Copper varies by cabinet distance, and a slow neighbour may be a pending upgrade."""
    assert verdict(None, now=NOW, street_best_mbps=Decimal(500)) == UNKNOWN
    assert verdict(None, now=NOW, street_best_mbps=Decimal(100)) == UNKNOWN


def test_inference_does_not_override_this_address() -> None:
    """An answer for this door was asked; the street is only reasoned from."""
    assert verdict(answer(30), now=NOW, street_best_mbps=Decimal(1000)) == FRESH


def test_inference_beats_a_stale_answer() -> None:
    """Both are evidence, and the street being fibre does not go out of date the same way."""
    assert verdict(answer(-1), now=NOW, street_best_mbps=Decimal(1000)) == INFERRED


def test_inference_beats_a_refusal_from_an_unfinished_scan() -> None:
    """A door not yet connected on a fibre street is worth offering, not writing off."""
    assert verdict(None, now=NOW, street_no=7, checked_to=14,
                   street_best_mbps=Decimal(1000)) == INFERRED


def test_inference_is_not_a_reason_to_ask() -> None:
    assert INFERRED not in ASK


def test_fibre_on_the_street_needs_no_asking() -> None:
    """The register files 712,026 fibre rows with no band at all, so speed alone misses them."""
    assert verdict(None, now=NOW, street_fibre=True) == INFERRED
    assert verdict(None, now=NOW, street_fibre=True, street_best_mbps=None) == INFERRED


def test_copper_on_the_street_is_still_asked() -> None:
    assert verdict(None, now=NOW, street_fibre=False, street_best_mbps=Decimal(100)) == UNKNOWN


def test_a_refusal_is_not_the_same_as_silence() -> None:
    """They were asked outright and said no. That leaves no row in availability to find, so
    without this the answer looks like one nobody has ever sought, and gets sought again."""
    assert verdict(None, now=NOW, refused=True) == REFUSED
    assert verdict(None, now=NOW, refused=False) == UNKNOWN


def test_a_refusal_does_not_survive_a_fibre_street() -> None:
    """A door not yet connected on a fibre street is worth offering, not writing off."""
    assert verdict(None, now=NOW, refused=True, street_fibre=True) == INFERRED
