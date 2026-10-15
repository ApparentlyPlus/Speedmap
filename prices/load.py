"""Record today's catalogue from every provider that publishes one."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from datetime import UTC, date, datetime

from db.connect import connect
from prices import nova, published, vodafone
from prices.catalogue import Tariff, write

SOURCES: dict[str, Callable[[], list[Tariff]]] = {"VODAFONE": vodafone.fetch, "NOVA": nova.fetch}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--on", type=date.fromisoformat, default=datetime.now(UTC).date())
    args = parser.parse_args(argv)

    failed = 0
    with connect() as conn:
        for provider, fetch in SOURCES.items():
            # skip a broken one, yesterday's price beats none
            try:
                tariffs = fetch()
            except Exception as e:
                print(f"  {provider}: {e}")
                failed += 1
                continue
            n = write(conn, provider, tariffs, args.on)
            conn.commit()
            print(f"  {provider}: {n} plans priced")

        # hand recorded, dated by when the page was read
        for provider, tariffs, day in published.sections():
            n = write(conn, provider, tariffs, day, source="published")
            conn.commit()
            print(f"  {provider}: {n} plans published {day}")
    return 1 if failed == len(SOURCES) else 0


if __name__ == "__main__":
    sys.exit(main())
