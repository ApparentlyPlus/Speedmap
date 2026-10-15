from __future__ import annotations

from pathlib import Path

import psycopg
import pytest

from db.settings import Settings
from tools.bootstrap import STAGES, Stage, database, misordered, skipped

ADMIN_DSN = "postgresql:///postgres"
SCRATCH = "speedmap_bootstrap_scratch"
MISSING = (Path("/nonexistent/file"),)


def _stage(name: str) -> Stage:
    return next(s for s in STAGES if s.name == name)


def _reachable() -> bool:
    try:
        psycopg.connect(ADMIN_DSN, connect_timeout=2).close()
    except psycopg.OperationalError:
        return False
    return True


def test_order() -> None:
    order = [s.name for s in STAGES]
    assert misordered(STAGES) == []
    # the easy one to miss, builders only get coverage where there's a tariff
    assert "prices" in _stage("build").after
    assert order.index("prices") < order.index("build")
    assert order[0] == "database"
    assert order[1] == "migrate"
    for s in STAGES:
        if s.name not in ("database", "migrate"):
            assert "migrate" in s.after or "migrate" in _stage(s.after[0]).after
    assert order[-1] == "build"


def test_misordered() -> None:
    first = Stage("first", lambda: 0, "does first")
    second = Stage("second", lambda: 0, "does second", after=("first",))
    assert misordered((first, second)) == []
    assert misordered((second, first)) == ["second runs before first"]
    assert "build runs before prices" in misordered(tuple(reversed(STAGES)))


def test_skipped() -> None:
    scrape = _stage("scrape")
    assert scrape.optional
    assert "326,249" in scrape.missing
    assert "still runs" in scrape.missing

    assert skipped(Stage("x", lambda: 0, "does x", optional=True, missing="nothing here", needs=MISSING)) == "nothing here"
    why = skipped(Stage("x", lambda: 0, "does x", needs=MISSING))
    assert why is not None
    assert "not found" in why
    assert skipped(Stage("x", lambda: 0, "does x")) is None
    assert skipped(_stage("migrate")) is None


# It used to return the number of databases created, so a fresh machine printed
# "[database] failed" once and then worked on the second run.
@pytest.mark.skipif(not _reachable(), reason=f"no postgres at {ADMIN_DSN}")
def test_database(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("tools.bootstrap.settings", Settings(dsn=f"postgresql:///{SCRATCH}"))
    with psycopg.connect(ADMIN_DSN, autocommit=True) as admin:
        admin.execute(f"drop database if exists {SCRATCH} with (force)")
    try:
        assert database() == 0
        with psycopg.connect(ADMIN_DSN, autocommit=True) as admin:
            found = admin.execute("select 1 from pg_database where datname = %s", (SCRATCH,)).fetchone()
        assert found is not None
        assert database() == 0
    finally:
        with psycopg.connect(ADMIN_DSN, autocommit=True) as admin:
            admin.execute(f"drop database if exists {SCRATCH} with (force)")
