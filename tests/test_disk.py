from __future__ import annotations

import shutil
from collections import namedtuple
from pathlib import Path

import pytest

from alert.disk import short

Usage = namedtuple("Usage", "total used free")
GB = 10**9


def _usage(monkeypatch: pytest.MonkeyPatch, total: int, free: int) -> None:
    monkeypatch.setattr(shutil, "disk_usage", lambda path: Usage(total * GB, (total - free) * GB, free * GB))


def test_short(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _usage(monkeypatch, 100, 50)
    assert short((tmp_path,)) == []

    _usage(monkeypatch, 200, 15)
    assert short((tmp_path,)) == [f"{tmp_path}: 15.0 GB free of 200 GB"]

    # 16 GB card, a fifth free is still under 5 GB
    _usage(monkeypatch, 16, 3)
    assert len(short((tmp_path,))) == 1

    other = tmp_path / "backups"
    other.mkdir()
    _usage(monkeypatch, 100, 1)
    assert len(short((tmp_path, other))) == 1


def test_short_missing(tmp_path: Path) -> None:
    assert short((tmp_path / "srv" / "speedmap",)) == []
