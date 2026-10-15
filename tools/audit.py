"""Run the data invariants against a real built database (make check only sees the empty fixture)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from db.connect import connect

INVARIANTS = Path(__file__).parent.parent / "tests" / "invariants"

SHOWN = 5


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", help="override SPEEDMAP_DSN")
    args = parser.parse_args(argv)

    files = sorted(INVARIANTS.glob("*.sql"))
    if not files:
        raise SystemExit(f"no invariants in {INVARIANTS}")

    failures = 0
    with connect(args.dsn) as conn:
        for path in files:
            rows = conn.execute(path.read_text(encoding="utf-8")).fetchall()
            if not rows:
                print(f"  ok    {path.stem}")
                continue
            failures += 1
            print(f"  BROKE {path.stem}: {len(rows)} rows")
            for row in rows[:SHOWN]:
                print(f"          {row}")
            if len(rows) > SHOWN:
                print(f"          ... and {len(rows) - SHOWN} more")

    if failures:
        print(f"\n{failures} of {len(files)} invariants do not hold.")
        return 1
    print(f"\nall {len(files)} invariants hold.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
