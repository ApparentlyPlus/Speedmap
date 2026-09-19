"""Connection helpers. Every worker opens its own connection, so there is no pool here yet."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import psycopg

from db.settings import settings


@contextmanager
def connect(dsn: str | None = None, *, autocommit: bool = False) -> Iterator[psycopg.Connection]:
    with psycopg.connect(dsn or settings.dsn, autocommit=autocommit) as conn:
        yield conn
