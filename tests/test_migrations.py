"""
The migration runner: ordering, recording, and refusal to run over drift.
"""

from __future__ import annotations

from pathlib import Path

import psycopg
import pytest
from psycopg.rows import TupleRow

from normalise.migrate import Migration, discover, drifted, migrate


def scalar(conn: psycopg.Connection[TupleRow], sql: str) -> object:
    row = conn.execute(sql).fetchone()
    assert row is not None
    return row[0]


def test_migrations_apply_in_filename_order() -> None:
    versions = [m.version for m in discover()]
    assert versions == sorted(versions)


def test_every_migration_is_recorded(db: psycopg.Connection[TupleRow]) -> None:
    assert scalar(db, "select count(*) from schema_migration") == len(discover())


def test_rerun_applies_nothing(db: psycopg.Connection[TupleRow]) -> None:
    assert migrate(db) == []


def test_checksum_follows_content(tmp_path: Path) -> None:
    first = tmp_path / "0001_a.sql"
    first.write_text("select 1;")
    second = tmp_path / "0002_b.sql"
    second.write_text("select 2;")

    assert Migration.load(first).checksum == Migration.load(first).checksum
    assert Migration.load(first).checksum != Migration.load(second).checksum


def test_edited_migration_is_drift() -> None:
    available = discover()
    known = {m.version: m.checksum for m in available}
    known[available[0].version] = "changed"
    assert drifted(known, available) == [available[0].version]


def test_migrate_refuses_to_run_over_drift(db: psycopg.Connection[TupleRow]) -> None:
    """An applied file edited after the fact must stop the run, not diverge quietly."""
    original = discover()[0]
    db.execute(
        "update schema_migration set checksum = 'tampered' where version = %s",
        (original.version,),
    )
    db.commit()
    try:
        with pytest.raises(SystemExit, match=original.version):
            migrate(db)
    finally:
        db.execute(
            "update schema_migration set checksum = %s where version = %s",
            (original.checksum, original.version),
        )
        db.commit()


def test_extensions_installed(db: psycopg.Connection[TupleRow]) -> None:
    rows = db.execute(
        "select extname from pg_extension where extname in ('postgis', 'pg_trgm', 'unaccent')"
    ).fetchall()
    assert sorted(name for (name,) in rows) == ["pg_trgm", "postgis", "unaccent"]
