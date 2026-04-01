"""
Configuration precedence: environment over .env over defaults.
"""

from __future__ import annotations

import pytest
from pydantic_settings import SettingsConfigDict

from db.settings import Settings


class Isolated(Settings):
    """Settings with no .env, so defaults are observable."""

    model_config = SettingsConfigDict(env_prefix="SPEEDMAP_", extra="ignore")


def test_environment_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPEEDMAP_DSN", "postgresql:///other")
    assert Isolated().dsn == "postgresql:///other"


def test_defaults_apply_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SPEEDMAP_DSN", raising=False)
    assert Isolated().dsn == "postgresql:///speedmap"


def test_prefix_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    """A bare DSN in the environment must not be picked up by accident."""
    monkeypatch.delenv("SPEEDMAP_DSN", raising=False)
    monkeypatch.setenv("DSN", "postgresql:///wrong")
    assert Isolated().dsn == "postgresql:///speedmap"
