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

STEPS = Path(__file__).parent / "steps"


# Steps that need real parsing live in Python; everything else is a .sql file.
PYTHON_STEPS: dict[str, Callable[[psycopg.Connection[TupleRow]], int]] = {
    "020_address": build_address_index,
}


@dataclass(frozen=True)
class Step:
    name: str
    run: Callable[[psycopg.Connection[TupleRow]], int]


def sql_step(path: Path) -> Step:
    def apply(conn: psycopg.Connection[TupleRow]) -> int:
        return conn.execute(path.read_text(encoding="utf-8")).rowcount

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
