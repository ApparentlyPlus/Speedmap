"""
A scratch database, rebuilt from the migrations once per session.
"""

from __future__ import annotations

from collections.abc import Iterator

import psycopg
import pytest
from psycopg.rows import TupleRow

from normalise.migrate import migrate

ADMIN_DSN = "postgresql:///postgres"
TEST_DSN = "postgresql:///speedmap_test"


def _server_reachable() -> bool:
    try:
        psycopg.connect(ADMIN_DSN, connect_timeout=2).close()
    except psycopg.OperationalError:
        return False
    return True


@pytest.fixture(scope="session")
def db() -> Iterator[psycopg.Connection[TupleRow]]:
    if not _server_reachable():
        pytest.skip(f"no postgres at {ADMIN_DSN}")

    with psycopg.connect(ADMIN_DSN, autocommit=True) as admin:
        admin.execute("drop database if exists speedmap_test with (force)")
        admin.execute("create database speedmap_test")

    with psycopg.connect(TEST_DSN) as conn:
        migrate(conn)
        yield conn


@pytest.fixture
def tx(db: psycopg.Connection[TupleRow]) -> Iterator[psycopg.Connection[TupleRow]]:
    """The session connection, rolled back after the test."""
    # Rollback cannot undo work that committed itself; code that commits needs a fixture that truncates instead.
    db.rollback()
    yield db
    db.rollback()


@pytest.fixture
def seeded(tx: psycopg.Connection[TupleRow]) -> psycopg.Connection[TupleRow]:
    """One provider and one source, enough to hang a coverage row off."""
    tx.execute("insert into provider (code, display_name, kind) values ('TEST', 'Test', 'altnet')")
    tx.execute("insert into source (name, url) values ('test', 'https://example.invalid')")
    return tx
