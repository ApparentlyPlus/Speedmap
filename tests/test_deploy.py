"""The units that run this without anyone typing anything.

A unit file is code that nobody runs in development and everybody depends on in production.
These check the things that rot quietly: a timer whose service was renamed, a job pointing
at a module that moved, a backup that stopped covering a table because the table was renamed.
"""

from __future__ import annotations

import configparser
import importlib.util
import re
from pathlib import Path

import psycopg
import pytest
from psycopg.rows import TupleRow

DEPLOY = Path(__file__).resolve().parent.parent / "deploy"

UNITS = sorted(DEPLOY.glob("*.service")) + sorted(DEPLOY.glob("*.timer"))
TIMERS = sorted(DEPLOY.glob("*.timer"))
SERVICES = sorted(DEPLOY.glob("*.service"))


def parsed(path: Path) -> configparser.ConfigParser:
    # Units allow a key more than once; ExecStart repeats to run steps in order.
    unit = configparser.ConfigParser(strict=False)
    unit.optionxform = str  # type: ignore[method-assign, assignment]
    unit.read_string(path.read_text(encoding="utf-8"))
    return unit


@pytest.mark.parametrize("path", UNITS, ids=lambda p: p.name)
def test_a_unit_parses(path: Path) -> None:
    assert parsed(path).sections()


@pytest.mark.parametrize("path", TIMERS, ids=lambda p: p.name)
def test_a_timer_has_the_service_it_starts(path: Path) -> None:
    """A timer names its service by filename. Rename one and it fires into nothing."""
    assert path.with_suffix(".service").exists()


@pytest.mark.parametrize("path", TIMERS, ids=lambda p: p.name)
def test_a_missed_run_catches_up(path: Path) -> None:
    """A Pi that was off at half two must still sweep when it comes back: the addresses
    nobody visits are exactly the ones that otherwise never get refreshed."""
    assert parsed(path)["Timer"]["Persistent"] == "true"


@pytest.mark.parametrize("path", TIMERS, ids=lambda p: p.name)
def test_a_timer_says_when(path: Path) -> None:
    assert parsed(path)["Timer"]["OnCalendar"]


@pytest.mark.parametrize("path", SERVICES, ids=lambda p: p.name)
def test_a_service_runs_something_that_exists(path: Path) -> None:
    """Every python -m in a unit names a module in this repository, or the job is a no-op
    that reports success every night for months."""
    for line in path.read_text(encoding="utf-8").splitlines():
        found = re.search(r"ExecStart=.*-m\s+([\w.]+)", line)
        if found is not None:
            assert importlib.util.find_spec(found.group(1)) is not None, found.group(1)


@pytest.mark.parametrize("path", SERVICES, ids=lambda p: p.name)
def test_a_job_is_not_run_as_root(path: Path) -> None:
    assert parsed(path)["Service"]["User"] == "speedmap"


def test_the_backup_covers_what_cannot_be_rebuilt(db: psycopg.Connection[TupleRow]) -> None:
    """Everything else is the register verbatim or derived from it. These five are answers
    operators gave, prices on the day we read them, and what people told us was wrong."""
    script = (DEPLOY / "backup.sh").read_text(encoding="utf-8")
    named = set(re.findall(r"--table=(\w+)", script))
    assert named == {"availability", "probe_attempt", "plan", "plan_price", "report"}

    stored = {
        str(name) for (name,) in db.execute(
            "select table_name from information_schema.tables where table_schema = 'public'"
        ).fetchall()
    }
    assert named <= stored


def test_the_backup_renames_only_once_whole() -> None:
    """A dump that was interrupted must never be mistaken for one that finished."""
    script = (DEPLOY / "backup.sh").read_text(encoding="utf-8")
    assert "--file=\"$out.partial\"" in script
    assert 'mv "$out.partial" "$out"' in script
    assert "set -euo pipefail" in script


# the one process in front of everything


CADDYFILE = DEPLOY / "Caddyfile"


def caddyfile() -> str:
    return CADDYFILE.read_text(encoding="utf-8")


def test_every_route_is_served_by_the_one_document() -> None:
    """The app has four routes and one file. A reader who arrives at /map directly, or
    reloads on it, must get the app rather than a 404 for a file that never existed."""
    assert "try_files {path} /index.html" in caddyfile()


def test_the_api_is_on_the_same_origin() -> None:
    """Same origin means no CORS to configure and nothing to get wrong about credentials."""
    body = caddyfile()
    assert "handle_path /api/*" in body
    assert "reverse_proxy 127.0.0.1:8000" in body


def test_a_probe_is_given_longer_than_a_page() -> None:
    """A live probe waits on an operator's own checker, which takes between two and eight
    seconds and occasionally never answers at all."""
    assert re.search(r"response_header_timeout\s+\d+s", caddyfile())


def test_hashed_assets_are_held_and_pages_are_not() -> None:
    body = caddyfile()
    assert "immutable" in body
    assert 'header Cache-Control "no-cache"' in body


def test_the_policy_allows_what_the_map_actually_needs() -> None:
    """MapLibre runs its work in a worker created from a blob, and draws into a canvas it
    reads back as a blob. A policy that forbids either gives a blank map and no error."""
    policy = next(line for line in caddyfile().splitlines() if "Content-Security-Policy" in line)
    assert "worker-src 'self' blob:" in policy
    assert "blob:" in policy.split("img-src")[1].split(";")[0]


def test_nothing_is_loaded_from_anywhere_else() -> None:
    """No basemap, no font CDN, no analytics: the policy should say so rather than allow a
    hole for something that was removed."""
    policy = next(line for line in caddyfile().splitlines() if "Content-Security-Policy" in line)
    assert "default-src 'self'" in policy
    assert "http://" not in policy
