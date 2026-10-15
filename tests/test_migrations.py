from __future__ import annotations

from pathlib import Path

import psycopg
import pytest
from psycopg.rows import TupleRow

from normalise.migrate import Migration, discover, drifted, migrate


def _one(conn: psycopg.Connection[TupleRow], sql: str) -> object:
    row = conn.execute(sql).fetchone()
    assert row is not None
    return row[0]


def test_migrate(db: psycopg.Connection[TupleRow]) -> None:
    versions = [m.version for m in discover()]
    assert versions == sorted(versions)
    assert _one(db, "select count(*) from schema_migration") == len(discover())
    assert migrate(db) == []

    rows = db.execute("select extname from pg_extension where extname in ('postgis', 'pg_trgm', 'unaccent')").fetchall()
    assert sorted(name for (name,) in rows) == ["pg_trgm", "postgis", "unaccent"]


def test_checksum(tmp_path: Path) -> None:
    first = tmp_path / "0001_a.sql"
    first.write_text("select 1;")
    second = tmp_path / "0002_b.sql"
    second.write_text("select 2;")
    assert Migration.load(first).checksum == Migration.load(first).checksum
    assert Migration.load(first).checksum != Migration.load(second).checksum

    available = discover()
    known = {m.version: m.checksum for m in available}
    known[available[0].version] = "changed"
    assert drifted(known, available) == [available[0].version]


def test_migrate_drift(db: psycopg.Connection[TupleRow]) -> None:
    original = discover()[0]
    db.execute("update schema_migration set checksum = 'tampered' where version = %s", (original.version,))
    db.commit()
    try:
        with pytest.raises(SystemExit, match=original.version):
            migrate(db)
    finally:
        db.execute("update schema_migration set checksum = %s where version = %s", (original.checksum, original.version))
        db.commit()


def test_migrate_broken(db: psycopg.Connection[TupleRow], tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # the SQL error surfaces, not one from unlocking an aborted transaction
    broken = tmp_path / "9999_broken.sql"
    broken.write_text("select * from no_such_table;")
    monkeypatch.setattr("normalise.migrate.discover", lambda: [*discover(), Migration.load(broken)])
    with pytest.raises(psycopg.errors.UndefinedTable):
        migrate(db)
    assert _one(db, "select count(*) from pg_locks where locktype = 'advisory'") == 0
    assert _one(db, "select count(*) from schema_migration where version = '9999_broken'") == 0
