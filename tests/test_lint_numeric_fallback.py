from __future__ import annotations

from pathlib import Path

from tools.lint_numeric_fallback import check_source

HERE = Path("t.py")


def _codes(source: str) -> list[str]:
    return [f.code for f in check_source(source, HERE)]


def test_or_fallback() -> None:
    for source in [
        "speed = row.get('maxdown') or 0",
        "speed = row.get('maxdown') or 0.0",
        "premises = prempass or 1",
        "offset = start or -1",
        "mbps = a or b or 25",
        "return best_mbps or 0",
    ]:
        assert _codes(source) == ["SM001"]
    # a measured 0 is a fact, or turns it into 25
    assert _codes("displayed = measured_mbps or 25") == ["SM001"]

    for source in [
        "name = row.get('street') or ''",
        "rows = fetched or []",
        "flag = explicit or False",
        "x = a and 0",
        "speed = row.get('maxdown')",
    ]:
        assert _codes(source) == []


def test_get_default() -> None:
    assert _codes("speed = row.get('maxdown', 0)") == ["SM002"]
    assert _codes("speed = getattr(offer, 'down_mbps', 0)") == ["SM002"]
    assert _codes("speed = row.get('maxdown')") == []
    assert _codes("street = row.get('street', '')") == []


def test_allow_fallback() -> None:
    assert _codes("delay = configured or 1.0  # allow-fallback: tuning knob, not a fact") == []
    assert _codes("speed = row.get('maxdown') or 0  # allow-fallback:") == ["SM001"]

    source = "delay = configured or 1.0  # allow-fallback: tuning knob\nspeed = row.get('maxdown') or 0\n"
    findings = check_source(source, HERE)
    assert [(f.code, f.line) for f in findings] == [("SM001", 2)]
