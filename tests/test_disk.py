"""Noticing the Pi's disk filling before Postgres does."""

from __future__ import annotations

import shutil
from collections import namedtuple
from pathlib import Path

import pytest

from alert.disk import short

Usage = namedtuple("Usage", "total used free")
GB = 10**9


def test_a_disk_with_room_says_nothing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(shutil, "disk_usage", lambda path: Usage(100 * GB, 50 * GB, 50 * GB))
    assert short((tmp_path,)) == []


def test_a_tenth_left_is_too_little(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(shutil, "disk_usage", lambda path: Usage(200 * GB, 185 * GB, 15 * GB))
    assert short((tmp_path,)) == [f"{tmp_path}: 15.0 GB free of 200 GB"]


def test_a_small_card_is_judged_by_gigabytes_too(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A fifth of a 16 GB card is under the floor even though the share looks healthy."""
    monkeypatch.setattr(shutil, "disk_usage", lambda path: Usage(16 * GB, 13 * GB, 3 * GB))
    assert len(short((tmp_path,))) == 1


def test_one_disk_is_reported_once(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    other = tmp_path / "backups"
    other.mkdir()
    monkeypatch.setattr(shutil, "disk_usage", lambda path: Usage(100 * GB, 99 * GB, 1 * GB))
    assert len(short((tmp_path, other))) == 1


def test_a_path_this_machine_does_not_have_is_skipped(tmp_path: Path) -> None:
    assert short((tmp_path / "srv" / "speedmap",)) == []
