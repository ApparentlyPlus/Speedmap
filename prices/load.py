"""Record today's catalogue from every provider that publishes one.

A provider that cannot be read is reported and skipped: a missing catalogue must not empty
the ones already recorded, and yesterday's price is a better answer than none.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from datetime import UTC, date, datetime

from db.connect import connect
from prices import nova, published, vodafone
from prices.catalogue import Tariff, write

SOURCES: dict[str, Callable[[], list[Tariff]]] = {
    "VODAFONE": vodafone.fetch,
    "NOVA": nova.fetch,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--on", type=date.fromisoformat, default=datetime.now(UTC).date())
    args = parser.parse_args(argv)

    failed = 0
    with connect() as conn:
        for provider, fetch in SOURCES.items():
            try:
                tariffs = fetch()
            except Exception as error:
                print(f"  {provider}: {error}")
                failed += 1
                continue
            written = write(conn, provider, tariffs, args.on)
            conn.commit()
            print(f"  {provider}: {written} plans priced")

        # Recorded by hand against a page or a rate card, and dated by when it was read
        # rather than by today: a figure from June is not evidence about September.
        for provider, (tariffs, observed_on) in published.load().items():
            written = write(conn, provider, tariffs, observed_on, source="published")
            conn.commit()
            print(f"  {provider}: {written} plans published {observed_on}")
    return 1 if failed == len(SOURCES) else 0


if __name__ == "__main__":
    sys.exit(main())
