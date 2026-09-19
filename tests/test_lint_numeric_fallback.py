"""Linter tests for numeric fallback rules."""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.lint_numeric_fallback import check_source

HERE = Path("t.py")


def codes(source: str) -> list[str]:
    return [f.code for f in check_source(source, HERE)]


# SM001: `or <number>`.


@pytest.mark.parametrize(
    "source",
    [
        "speed = row.get('maxdown') or 0",
        "speed = row.get('maxdown') or 0.0",
        "premises = prempass or 1",
        "offset = start or -1",
        "mbps = a or b or 25",
        "return best_mbps or 0",
    ],
)
def test_flags_numeric_or_fallback(source: str) -> None:
    assert codes(source) == ["SM001"]


@pytest.mark.parametrize(
    "source",
    [
        # Non-numeric defaults are a different question and not this rule's job.
        "name = row.get('street') or ''",
        "rows = fetched or []",
        "flag = explicit or False",
        # `and` cannot introduce a value.
        "x = a and 0",
        # A bare read is exactly what we want people to write.
        "speed = row.get('maxdown')",
    ],
)
def test_ignores_non_numeric_and_safe_forms(source: str) -> None:
    assert codes(source) == []


# SM002: `.get(key.


def test_flags_dict_get_numeric_default() -> None:
    assert codes("speed = row.get('maxdown', 0)") == ["SM002"]


def test_flags_getattr_numeric_default() -> None:
    assert codes("speed = getattr(offer, 'down_mbps', 0)") == ["SM002"]


def test_ignores_single_argument_get() -> None:
    assert codes("speed = row.get('maxdown')") == []


def test_ignores_non_numeric_get_default() -> None:
    assert codes("street = row.get('street', '')") == []


# suppression.


def test_suppressed_with_a_reason() -> None:
    source = "delay = configured or 1.0  # allow-fallback: tuning knob, not a fact"
    assert codes(source) == []


def test_not_suppressed_without_a_reason() -> None:
    source = "speed = row.get('maxdown') or 0  # allow-fallback:"
    assert codes(source) == ["SM001"]


def test_suppression_is_per_line() -> None:
    source = (
        "delay = configured or 1.0  # allow-fallback: tuning knob\n"
        "speed = row.get('maxdown') or 0\n"
    )
    findings = check_source(source, HERE)
    assert [(f.code, f.line) for f in findings] == [("SM001", 2)]


# Regression tests.


def test_zero_is_falsy_bug_is_caught() -> None:
    """A measured 0 Mbps is a fact. `or` rewrites it into the default."""
    assert codes("displayed = measured_mbps or 25") == ["SM001"]
