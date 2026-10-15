"""Apply ordered SQL migrations. Each file in migrations/ runs once."""

from __future__ import annotations

import argparse
import hashlib
import sys
from dataclasses import dataclass
from pathlib import Path

import psycopg
from psycopg.rows import TupleRow

from db.connect import connect

MIGRATIONS = Path(__file__).parent / "migrations"

LOCK_KEY = 8104729  # advisory lock, two runners take turns

BOOTSTRAP = """
create table if not exists schema_migration (
    version text primary key,
    checksum text not null,
    applied_at timestamptz not null default now()
)
"""


@dataclass(frozen=True)
class Migration:
    version: str
    path: Path
    checksum: str

    @classmethod
    def load(cls, path: Path) -> Migration:
        body = path.read_bytes()
        return cls(path.stem, path, hashlib.sha256(body).hexdigest())

    def sql(self) -> str:
        return self.path.read_text(encoding="utf-8")


def discover() -> list[Migration]:
    return [Migration.load(p) for p in sorted(MIGRATIONS.glob("*.sql"))]


def applied(conn: psycopg.Connection[TupleRow]) -> dict[str, str]:
    rows = conn.execute("select version, checksum from schema_migration").fetchall()
    return dict(rows)


def drifted(done: dict[str, str], ms: list[Migration]) -> list[str]:
    return [m.version for m in ms if m.version in done and done[m.version] != m.checksum]


def pending(done: dict[str, str], ms: list[Migration]) -> list[Migration]:
    return [m for m in ms if m.version not in done]


def migrate(conn: psycopg.Connection[TupleRow], *, dry_run: bool = False) -> list[str]:
    conn.execute(BOOTSTRAP)
    conn.commit()
    conn.execute("select pg_advisory_lock(%s)", (LOCK_KEY,))
    try:
        ms = discover()
        done = applied(conn)

        drift = drifted(done, ms)
        if drift:
            raise SystemExit(f"already applied but changed on disk: {', '.join(drift)}")

        todo = pending(done, ms)
        if dry_run:
            return [m.version for m in todo]

        for m in todo:
            conn.execute(m.sql())
            conn.execute("insert into schema_migration (version, checksum) values (%s, %s)", (m.version, m.checksum))
            conn.commit()
            print(f"applied {m.version}")
        return [m.version for m in todo]
    finally:
        # a failed migration leaves the transaction aborted and the unlock would fail too
        conn.rollback()
        conn.execute("select pg_advisory_unlock(%s)", (LOCK_KEY,))
        conn.commit()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--status", action="store_true", help="list pending migrations only")
    parser.add_argument("--dsn", help="override SPEEDMAP_DSN")
    args = parser.parse_args(argv)

    with connect(args.dsn) as conn:
        todo = migrate(conn, dry_run=args.status)

    if args.status:
        print("\n".join(todo) if todo else "up to date")
    elif not todo:
        print("up to date")
    return 0


if __name__ == "__main__":
    sys.exit(main())
