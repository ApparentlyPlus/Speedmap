"""Bring an empty machine to a running speedmap.

Every stage is idempotent, so this is the same command whether it is the first run or the
fifth: the register load resumes from its own key, downloads are skipped if the file is
there, migrations are once-only and the derived tables are rebuilt from scratch each time.

The order is not a matter of taste. It is declared here and checked before anything runs,
because one of the dependencies is invisible: the build only gives a network builder
coverage if a tariff for them is already on record, so building before prices silently
leaves 129,529 addresses without the one fibre option they have.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import psycopg
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from db.settings import settings

# The operator's scrape. Months of someone's asking, several gigabytes, and not something
# a clone can reproduce. Everything works without it and rather less well: see skipped().
SCRAPE = Path("data/cosmote.db")

# Connected to in order to create the real one, because a database cannot create itself.
MAINTENANCE = "postgres"


@dataclass(frozen=True)
class Stage:
    name: str
    run: Callable[[], int]
    does: str
    after: tuple[str, ...] = ()
    optional: bool = False
    missing: str = ""
    needs: Sequence[Path] = field(default_factory=tuple)


def database() -> int:
    """Create the database if it is not there. Nothing else in the repository does."""
    info = conninfo_to_dict(settings.dsn)
    name = str(info.get("dbname", "speedmap"))
    admin = make_conninfo(settings.dsn, dbname=MAINTENANCE)
    with psycopg.connect(admin, autocommit=True) as conn:
        found = conn.execute(
            "select 1 from pg_database where datname = %s", (name,)
        ).fetchone()
        if found is not None:
            return 0
        # Not parameterisable: an identifier, not a value.
        conn.execute(psycopg.sql.SQL("create database {}").format(psycopg.sql.Identifier(name)))
    return 1


def migrate() -> int:
    from normalise.migrate import main

    return main([])


def register() -> int:
    from ingest.load import main

    return main([])


def osm() -> int:
    from ingest.osm import main

    return main([])


def ookla() -> int:
    from ingest.ookla import main

    return main(["--latest"])


def scrape() -> int:
    from ingest.cosmote import main

    return main([])


def prices() -> int:
    from prices.load import main

    return main([])


def build() -> int:
    from normalise.build import main

    return main([])


STAGES: tuple[Stage, ...] = (
    Stage("database", database, "create the database"),
    Stage("migrate", migrate, "apply the schema", after=("database",)),
    Stage("register", register, "load the national register", after=("migrate",)),
    Stage("osm", osm, "load named streets", after=("migrate",)),
    Stage("ookla", ookla, "load what people measured", after=("migrate",)),
    Stage(
        "scrape", scrape, "load the operator scrape", after=("migrate",),
        optional=True, needs=(SCRAPE,),
        missing=(
            "no operator scrape: the address index loses 326,249 addresses, two of the "
            "three checkers can only be asked about streets it walked, and 1.2M cached "
            "answers start empty. Everything still runs."
        ),
    ),
    # Before the build, and this is the dependency that is easy to miss.
    Stage("prices", prices, "load the tariff catalogues", after=("migrate",)),
    Stage(
        "build", build, "derive everything from the raw tables",
        after=("register", "osm", "ookla", "scrape", "prices"),
    ),
)


def misordered(stages: Sequence[Stage]) -> list[str]:
    """Any stage declared before something it depends on."""
    seen: set[str] = set()
    wrong: list[str] = []
    for stage in stages:
        wrong += [f"{stage.name} runs before {need}" for need in stage.after if need not in seen]
        seen.add(stage.name)
    return wrong


def skipped(stage: Stage) -> str | None:
    """Why this stage will not run, if it will not."""
    absent = [path for path in stage.needs if not path.exists()]
    if not absent:
        return None
    if stage.optional:
        return stage.missing
    return f"{', '.join(str(p) for p in absent)} not found"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip", action="append", default=[], help="a stage to leave out")
    parser.add_argument("--only", action="append", default=[], help="a stage to run alone")
    parser.add_argument("--dry-run", action="store_true", help="say what would happen")
    args = parser.parse_args(argv)

    wrong = misordered(STAGES)
    if wrong:
        print("stages are out of order: " + "; ".join(wrong))
        return 1

    known = {stage.name for stage in STAGES}
    unknown = set(args.skip) | set(args.only)
    if not unknown <= known:
        parser.error(f"unknown stage(s): {', '.join(sorted(unknown - known))}")

    for stage in STAGES:
        if stage.name in args.skip or (args.only and stage.name not in args.only):
            continue
        why = skipped(stage)
        if why is not None:
            print(f"[skip] {stage.name}: {why}")
            if not stage.optional:
                return 1
            continue
        print(f"[{stage.name}] {stage.does}")
        if args.dry_run:
            continue
        code = stage.run()
        if code != 0:
            print(f"[{stage.name}] failed")
            return code
    return 0


if __name__ == "__main__":
    sys.exit(main())
