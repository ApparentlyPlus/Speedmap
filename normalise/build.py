"""Rebuild the derived tables from raw_*.

Unlike a migration a step is re-runnable, so each is written to be idempotent and is
never checksummed: rerunning after a fresh register pull is the normal case.
"""

from __future__ import annotations

import argparse
import sys
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


# Steps that need real parsing live in Python; everything else is a .sql file.
PYTHON_STEPS: dict[str, Callable[[psycopg.Connection[TupleRow]], int]] = {
    "020_address": build_address_index,
    "060_street": build_street_index,
    "080_cosmote": build_cosmote,
}


@dataclass(frozen=True)
class Step:
    name: str
    run: Callable[[psycopg.Connection[TupleRow]], int]


def sql_step(path: Path) -> Step:
    def apply(conn: psycopg.Connection[TupleRow]) -> int:
        """Rows written by the whole file, not by the first statement in it.

        psycopg leaves the cursor on the first result of a multi-statement execute, so a
        step that clears before it writes reported the size of the delete and stopped. Every
        step used to be a single insert and it did not matter; now that each one clears its
        own work first — see migration 0047 — it reported "050_address_coverage: 0 rows"
        while writing ten million of them, which is the build log saying nothing happened
        during the four minutes it took to happen.

        Summed across the statements, since what the line is for is "did this do anything".
        """
        cursor = conn.execute(path.read_text(encoding="utf-8"))
        written = 0
        while True:
            # -1 is "this statement had no row count", which a truncate reports.
            written += max(cursor.rowcount, 0)
            if not cursor.nextset():
                return written

    return Step(path.stem, apply)


def discover() -> list[Step]:
    steps = [sql_step(p) for p in STEPS.glob("*.sql")]
    steps += [Step(name, fn) for name, fn in PYTHON_STEPS.items()]
    return sorted(steps, key=lambda s: s.name)


def run(conn: psycopg.Connection[TupleRow], steps: list[Step]) -> dict[str, int]:
    written: dict[str, int] = {}
    for step in steps:
        written[step.name] = step.run(conn)
        conn.commit()
        print(f"  {step.name}: {written[step.name]} rows")
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Rebuild derived tables from raw_*")
    parser.add_argument("steps", nargs="*", help="default: all of them, in order")
    args = parser.parse_args(argv)

    available = discover()
    known = {s.name for s in available}
    unknown = [n for n in args.steps if n not in known]
    if unknown:
        parser.error(f"unknown step(s): {', '.join(unknown)}")

    chosen = [s for s in available if s.name in args.steps] if args.steps else available
    with connect() as conn:
        run(conn, chosen)
    return 0


if __name__ == "__main__":
    sys.exit(main())
