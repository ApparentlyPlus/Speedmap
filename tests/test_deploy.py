from __future__ import annotations

import configparser
import importlib.util
import re
from pathlib import Path

import psycopg
from psycopg.rows import TupleRow

DEPLOY = Path(__file__).resolve().parent.parent / "deploy"

UNITS = sorted(DEPLOY.glob("*.service")) + sorted(DEPLOY.glob("*.timer"))
TIMERS = sorted(DEPLOY.glob("*.timer"))
SERVICES = sorted(DEPLOY.glob("*.service"))
CADDYFILE = (DEPLOY / "Caddyfile").read_text(encoding="utf-8")


def _unit(path: Path) -> configparser.ConfigParser:
    # repeated keys are fine in systemd, and % is theirs (%n, %i)
    unit = configparser.ConfigParser(strict=False, interpolation=None)
    unit.optionxform = str  # type: ignore[method-assign, assignment]
    unit.read_string(path.read_text(encoding="utf-8"))
    return unit


def test_units() -> None:
    for path in UNITS:
        assert _unit(path).sections(), path.name

    for path in TIMERS:
        assert path.with_suffix(".service").exists(), path.name
        # a Pi that was off at 02:30 still runs it
        assert _unit(path)["Timer"]["Persistent"] == "true", path.name
        assert _unit(path)["Timer"]["OnCalendar"], path.name

    for path in SERVICES:
        for line in path.read_text(encoding="utf-8").splitlines():
            found = re.search(r"ExecStart=.*-m\s+([\w.]+)", line)
            if found is not None:
                assert importlib.util.find_spec(found.group(1)) is not None, found.group(1)
        assert _unit(path)["Service"]["User"] == "speedmap", path.name

    for path in SERVICES:
        if "@" not in path.name:
            assert _unit(path)["Unit"]["OnFailure"] == "speedmap-alert@%n.service", path.name

    alert = _unit(DEPLOY / "speedmap-alert@.service")["Service"]
    assert "-m alert --failed %i" in alert["ExecStart"]
    assert alert["SupplementaryGroups"] == "systemd-journal"

    # or every reader is 127.0.0.1 and they all share one limit
    command = _unit(DEPLOY / "speedmap-api.service")["Service"]["ExecStart"]
    assert "--proxy-headers" in command
    assert "--forwarded-allow-ips 127.0.0.1" in command

    for name in ["speedmap-register.service", "speedmap-ookla.service"]:
        steps = [line for line in (DEPLOY / name).read_text().splitlines() if line.startswith("ExecStart=")]
        assert steps[-1].endswith("-m publish.run --out /srv/speedmap/tiles/speedmap.pmtiles")


def test_backup(db: psycopg.Connection[TupleRow]) -> None:
    # the only tables that can't be rebuilt from the register
    script = (DEPLOY / "backup.sh").read_text(encoding="utf-8")
    named = set(re.findall(r"--table=(\w+)", script))
    assert named == {"availability", "probe_attempt", "plan", "plan_price", "report"}
    q = "select table_name from information_schema.tables where table_schema = 'public'"
    assert named <= {str(name) for (name,) in db.execute(q).fetchall()}

    assert "--file=\"$out.partial\"" in script
    assert 'mv "$out.partial" "$out"' in script
    assert "set -euo pipefail" in script


def test_caddyfile() -> None:
    assert "try_files {path} /index.html" in CADDYFILE
    assert "handle_path /api/*" in CADDYFILE
    assert "reverse_proxy 127.0.0.1:8000" in CADDYFILE
    # a probe can take 2 to 8 seconds
    assert re.search(r"response_header_timeout\s+\d+s", CADDYFILE)
    assert "immutable" in CADDYFILE
    assert 'header Cache-Control "no-cache"' in CADDYFILE

    # MapLibre needs blob: workers and images or the map is blank with no error
    policy = next(line for line in CADDYFILE.splitlines() if "Content-Security-Policy" in line)
    assert "worker-src 'self' blob:" in policy
    assert "blob:" in policy.split("img-src")[1].split(";")[0]
    assert "default-src 'self'" in policy
    assert "http://" not in policy
