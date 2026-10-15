"""Bring an empty machine to a running speedmap. Every stage is idempotent, rerun freely."""

from __future__ import annotations

import argparse
import importlib
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import psycopg
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from db.settings import settings

# months of asking Telekom, a clone can't reproduce it
SCRAPE = Path("data/cosmote.db")

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
    info = conninfo_to_dict(settings.dsn)
    name = str(info.get("dbname", "speedmap"))
    admin = make_conninfo(settings.dsn, dbname=MAINTENANCE)
    with psycopg.connect(admin, autocommit=True) as conn:
        found = conn.execute("select 1 from pg_database where datname = %s", (name,)).fetchone()
        if found is None:
            conn.execute(psycopg.sql.SQL("create database {}").format(psycopg.sql.Identifier(name)))
            print(f"  created {name}")
    # 0 even when it created it, main() stops on anything else
    return 0


def module(name: str, *argv: str) -> Callable[[], int]:
    # imported late, so --dry-run doesn't need the pipeline deps
    def run() -> int:
        main: Callable[[list[str]], int] = importlib.import_module(name).main
        return main(list(argv))

    return run


STAGES: tuple[Stage, ...] = (
    Stage("database", database, "create the database"),
    Stage("migrate", module("normalise.migrate"), "apply the schema", after=("database",)),
    Stage("register", module("ingest.load"), "load the national register", after=("migrate",)),
    Stage("osm", module("ingest.osm"), "load named streets", after=("migrate",)),
    Stage("ookla", module("ingest.ookla", "--latest"), "load what people measured", after=("migrate",)),
    Stage(
        "scrape", module("ingest.cosmote"), "load the operator scrape", after=("migrate",),
        optional=True, needs=(SCRAPE,),
        missing=(
            "no operator scrape: the address index loses 326,249 addresses, two of the "
            "three checkers can only be asked about streets it walked, and 1.2M cached "
            "answers start empty. Everything still runs."
        ),
    ),
    Stage("prices", module("prices.load"), "load the tariff catalogues", after=("migrate",)),
    Stage("build", module("normalise.build"), "derive everything from the raw tables",
          after=("register", "osm", "ookla", "scrape", "prices")),
)


def misordered(stages: Sequence[Stage]) -> list[str]:
    seen: set[str] = set()
    wrong: list[str] = []
    for s in stages:
        wrong += [f"{s.name} runs before {need}" for need in s.after if need not in seen]
        seen.add(s.name)
    return wrong


def skipped(stage: Stage) -> str | None:
    absent = [p for p in stage.needs if not p.exists()]
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

    known = {s.name for s in STAGES}
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
