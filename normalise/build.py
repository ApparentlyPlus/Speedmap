"""Rebuild the derived tables from raw_*.

Steps differ from migrations: each is idempotent and never checksummed, since rerunning after a
fresh register pull is the normal case.
"""

from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import psycopg
from psycopg.rows import TupleRow

from db.connect import connect
from normalise.address_index import build_address_index
from normalise.cosmote import build_cosmote
from normalise.street_index import build_street_index

STEPS = Path(__file__).parent / "steps"

# Sort and hash memory for this connection only, so the API and probes keep the server
# default. The steps sort and hash millions of rows, and 4 MB sends that to disk, an SD
# card on the Pi. Generous because a build runs alone, four times a year.
SESSION = (
    "set work_mem = '128MB'",
    "set maintenance_work_mem = '512MB'",
)


# steps needing real parsing are Python, the rest are .sql files
PYTHON_STEPS: dict[str, Callable[[psycopg.Connection[TupleRow]], int]] = {
    "020_address": build_address_index,
    # Before 050 and 065. It adds addresses, and ones added after those ran got no coverage
    # and no street until the build after next.
    "045_cosmote": build_cosmote,
    "060_street": build_street_index,
}


@dataclass(frozen=True)
class Step:
    name: str
    run: Callable[[psycopg.Connection[TupleRow]], int]


def sql_step(path: Path) -> Step:
    def apply(conn: psycopg.Connection[TupleRow]) -> int:
        """Rows written by the whole file.

        psycopg leaves the cursor on the first result of a multi-statement execute, so a step
        that deletes before inserting reported the size of the delete.
        """
        cursor = conn.execute(path.read_text(encoding="utf-8"))
        counts = 0
        while True:
            # -1 means no row count, which is what a truncate reports
            counts += max(cursor.rowcount, 0)
            if not cursor.nextset():
                return counts

    return Step(path.stem, apply)


def discover() -> list[Step]:
    steps = [sql_step(p) for p in STEPS.glob("*.sql")]
    steps += [Step(name, fn) for name, fn in PYTHON_STEPS.items()]
    return sorted(steps, key=lambda s: s.name)


def run(conn: psycopg.Connection[TupleRow], steps: list[Step]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for step in steps:
        began = time.perf_counter()
        counts[step.name] = step.run(conn)
        conn.commit()
        took = time.perf_counter() - began
        print(f"  {step.name}: {counts[step.name]} rows in {took:.1f}s", flush=True)
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Rebuild derived tables from raw_*")
    parser.add_argument("steps", nargs="*", help="default: all of them, in order")
    args = parser.parse_args(argv)

    steps = discover()
    known = {s.name for s in steps}
    unknown = [n for n in args.steps if n not in known]
    if unknown:
        parser.error(f"unknown step(s): {', '.join(unknown)}")

    todo = [s for s in steps if s.name in args.steps] if args.steps else steps
    with connect() as conn:
        for setting in SESSION:
            conn.execute(setting)
        run(conn, todo)
    return 0


if __name__ == "__main__":
    sys.exit(main())
