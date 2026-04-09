"""Rebuild the derived tables from raw_*.

Unlike a migration a step is re-runnable, so each is written to be idempotent and is
never checksummed: rerunning after a fresh register pull is the normal case.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

import psycopg
from psycopg.rows import TupleRow

from db.connect import connect

STEPS = Path(__file__).parent / "steps"


@dataclass(frozen=True)
class Step:
    name: str
    path: Path

    def sql(self) -> str:
        return self.path.read_text(encoding="utf-8")


def discover() -> list[Step]:
    return [Step(p.stem, p) for p in sorted(STEPS.glob("*.sql"))]


def run(conn: psycopg.Connection[TupleRow], steps: list[Step]) -> dict[str, int]:
    written: dict[str, int] = {}
    for step in steps:
        cursor = conn.execute(step.sql())
        written[step.name] = cursor.rowcount
        conn.commit()
        print(f"  {step.name}: {cursor.rowcount} rows")
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
