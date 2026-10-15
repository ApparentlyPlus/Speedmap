from __future__ import annotations

import pytest
from pydantic_settings import SettingsConfigDict

from db.settings import Settings


class Isolated(Settings):
    model_config = SettingsConfigDict(env_prefix="SPEEDMAP_", extra="ignore")  # no .env


def test_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPEEDMAP_DSN", "postgresql:///other")
    assert Isolated().dsn == "postgresql:///other"

    monkeypatch.delenv("SPEEDMAP_DSN")
    assert Isolated().dsn == "postgresql:///speedmap"

    # a bare DSN mustn't get picked up
    monkeypatch.setenv("DSN", "postgresql:///wrong")
    assert Isolated().dsn == "postgresql:///speedmap"
