"""Rebuild the derived tables from raw_*. Steps are idempotent and rerun after every pull."""

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

# this connection only, the default 4MB spills to the Pi's SD card
SESSION = (
    "set work_mem = '128MB'",
    "set maintenance_work_mem = '512MB'",
)


PYTHON_STEPS: dict[str, Callable[[psycopg.Connection[TupleRow]], int]] = {
    "020_address": build_address_index,
    "045_cosmote": build_cosmote,  # adds addresses, so before 050 and 065
    "060_street": build_street_index,
}


@dataclass(frozen=True)
class Step:
    name: str
    run: Callable[[psycopg.Connection[TupleRow]], int]


def sql_step(path: Path) -> Step:
    def apply(conn: psycopg.Connection[TupleRow]) -> int:
        # sum every statement's rows, the cursor starts on the first result only
        cur = conn.execute(path.read_text(encoding="utf-8"))
        n = 0
        while True:
            n += max(cur.rowcount, 0)  # truncate gives -1
            if not cur.nextset():
                return n

    return Step(path.stem, apply)


def discover() -> list[Step]:
    steps = [sql_step(p) for p in STEPS.glob("*.sql")]
    steps += [Step(name, fn) for name, fn in PYTHON_STEPS.items()]
    return sorted(steps, key=lambda s: s.name)


def run(conn: psycopg.Connection[TupleRow], steps: list[Step]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for step in steps:
        t = time.perf_counter()
        counts[step.name] = step.run(conn)
        conn.commit()
        print(f"  {step.name}: {counts[step.name]} rows in {time.perf_counter() - t:.1f}s", flush=True)
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
