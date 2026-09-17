"""Run the data invariants against a database that has actually been built.

`make check` runs them too, and proves something different by it. There the database is a
scratch one rebuilt from the migrations and left empty, so every invariant returns no rows
whatever it asks; what the suite tests is that each one still fires when a violation is
planted under it. That is worth testing and it is not the same as the data being right.

Nothing ran them against the real thing. Two were failing there the whole time — one on
33,760 streets, 42% of the country, painted a speed with no operator behind them — while
the tree stayed green, because green meant "these queries work", not "this data holds".

So this is the other half: the same files, against whatever SPEEDMAP_DSN points at. It is
not part of `make check`, which has to pass on a laptop with no data loaded; it is what you
run after a build, and what a deploy should refuse on.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import psycopg
from psycopg.rows import TupleRow

from db.connect import connect

INVARIANTS = Path(__file__).parent.parent / "tests" / "invariants"

# Enough of a violation to recognise it, not enough to fill a terminal with the same shape
# of row four thousand times.
SHOWN = 5


def check(conn: psycopg.Connection[TupleRow], path: Path) -> list[TupleRow]:
    return conn.execute(path.read_text(encoding="utf-8")).fetchall()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", help="override SPEEDMAP_DSN")
    args = parser.parse_args(argv)

    files = sorted(INVARIANTS.glob("*.sql"))
    if not files:
        raise SystemExit(f"no invariants in {INVARIANTS}")

    broken = 0
    with connect(args.dsn) as conn:
        for path in files:
            found = check(conn, path)
            if not found:
                print(f"  ok    {path.stem}")
                continue
            broken += 1
            print(f"  BROKE {path.stem}: {len(found)} rows")
            for row in found[:SHOWN]:
                print(f"          {row}")
            if len(found) > SHOWN:
                print(f"          ... and {len(found) - SHOWN} more")

    if broken:
        print(f"\n{broken} of {len(files)} invariants do not hold.")
        return 1
    print(f"\nall {len(files)} invariants hold.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
