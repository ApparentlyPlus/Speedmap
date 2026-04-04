"""
Load the register into the raw_* tables.

Every page is committed with its resume key, so an interrupted run continues
rather than restarts. Work is network-bound at roughly 500 rows per request, so
the writes stay simple rather than batched through COPY.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

import httpx
import psycopg
from psycopg.rows import TupleRow

from db.connect import connect
from db.settings import settings
from ingest.register import BY_NAME, LOOKUPS, Dataset, RegisterClient, Row


class GeometryCrsError(RuntimeError):
    """A geometry arrived in a projection we were not expecting."""


@dataclass(frozen=True)
class Target:
    table: str
    keys: tuple[str, ...]
    # column -> the SRID the register serves it in
    geometry: Mapping[str, int] = field(default_factory=dict)


TARGETS: dict[str, Target] = {
    "provider": Target("raw_provider", ("id",)),
    "coverpoint": Target("raw_coverpoint", ("coverid",), {"point": 4326, "waitpoin": 4326}),
    "wiredservice": Target("raw_wiredservice", ("id",)),
    "coverage_ftth": Target("raw_coverage_ftth", ("id",), {"geom": 4326}),
    "coverage_copper": Target("raw_coverage_copper", ("id",), {"geom": 2100}),
    "geo_coverage_copper": Target("raw_geo_coverage_copper", ("coverid",), {"geom": 2100}),
}


def geojson_srid(value: Mapping[str, Any]) -> int | None:
    """The EPSG code from a GeoJSON crs member, or None when it carries no crs."""
    crs = value.get("crs")
    if not isinstance(crs, Mapping):
        return None
    properties = crs.get("properties")
    if not isinstance(properties, Mapping):
        return None
    name = str(properties.get("name", ""))
    _, _, code = name.rpartition(":")
    return int(code) if code.isdigit() else None


def geometry_param(column: str, value: object, expected: int) -> str | None:
    """Validate the projection, then hand PostGIS the raw GeoJSON."""
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise GeometryCrsError(f"{column}: expected GeoJSON, got {type(value).__name__}")
    found = geojson_srid(value)
    if found is not None and found != expected:
        raise GeometryCrsError(f"{column}: expected EPSG:{expected}, got EPSG:{found}")
    return json.dumps(value)


def upsert_sql(target: Target, columns: tuple[str, ...]) -> str:
    placeholders = [
        f"st_setsrid(st_geomfromgeojson(%s), {target.geometry[c]})"
        if c in target.geometry
        else "%s"
        for c in columns
    ]
    updatable = [c for c in columns if c not in target.keys]
    action = (
        "nothing"
        if not updatable
        else "update set " + ", ".join(f"{c} = excluded.{c}" for c in updatable)
    )
    return (
        f"insert into {target.table} ({', '.join(columns)}) "
        f"values ({', '.join(placeholders)}) "
        f"on conflict ({', '.join(target.keys)}) do {action}"
    )


def row_params(target: Target, columns: tuple[str, ...], row: Row) -> tuple[object, ...]:
    return tuple(
        geometry_param(c, row[c], target.geometry[c]) if c in target.geometry else row[c]
        for c in columns
    )


def write_page(conn: psycopg.Connection[TupleRow], target: Target, rows: Iterable[Row]) -> int:
    batch = list(rows)
    if not batch:
        return 0
    columns = tuple(batch[0])
    conn.cursor().executemany(
        upsert_sql(target, columns), [row_params(target, columns, r) for r in batch]
    )
    return len(batch)


def resume_key(conn: psycopg.Connection[TupleRow], dataset: str) -> str | None:
    conn.execute(
        "insert into register_fetch (dataset) values (%s) on conflict do nothing", (dataset,)
    )
    row = conn.execute(
        "select last_key from register_fetch where dataset = %s", (dataset,)
    ).fetchone()
    return None if row is None else row[0]


def record_progress(conn: psycopg.Connection[TupleRow], dataset: str, *,last_key: str,
    added: int, total: int | None,
) -> None:
    conn.execute(
        "update register_fetch set last_key = %s, fetched = fetched + %s, "
        "total = coalesce(%s, total), updated_at = now() where dataset = %s",
        (last_key, added, total, dataset),
    )


def load(conn: psycopg.Connection[TupleRow], client: RegisterClient, dataset: Dataset,*,
    max_pages: int | None = None,
) -> int:
    target = TARGETS[dataset.name]
    total = client.count(dataset)
    cap = client.page_cap(dataset)
    after = resume_key(conn, dataset.name)
    conn.commit()

    loaded = 0
    for page_number, page in enumerate(client.pages(dataset, cap=cap, after=after), start=1):
        loaded += write_page(conn, target, page)
        record_progress(
            conn,
            dataset.name,
            last_key=str(page[-1][dataset.key]),
            added=len(page),
            total=total,
        )
        conn.commit()
        print(f"  {dataset.name}: {loaded} rows", end="\r", file=sys.stderr)
        if max_pages is not None and page_number >= max_pages:
            break

    print(f"\r  {dataset.name}: {loaded} rows loaded ")
    return loaded


def load_lookups(conn: psycopg.Connection[TupleRow], client: RegisterClient) -> int:
    loaded = 0
    for table in LOOKUPS:
        for row in client.lookup(table):
            conn.execute(
                "insert into raw_lookup (table_name, id, description, long_description) "
                "values (%s, %s, %s, %s) on conflict (table_name, id) do update set "
                "description = excluded.description, "
                "long_description = excluded.long_description",
                (table, row["id"], row.get("description"), row.get("long_description")),
            )
            loaded += 1
    conn.commit()
    print(f"  lookups: {loaded} rows loaded")
    return loaded


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Load the register into raw_* tables")
    parser.add_argument("datasets", nargs="*", default=None, help="default: all of them")
    parser.add_argument("--max-pages", type=int, help="stop early, for a smoke test")
    parser.add_argument("--skip-lookups", action="store_true")
    args = parser.parse_args(argv)

    names = args.datasets if args.datasets else list(BY_NAME)
    unknown = [n for n in names if n not in BY_NAME]
    if unknown:
        parser.error(f"unknown dataset(s): {', '.join(unknown)}")

    http = httpx.Client(headers={"user-agent": settings.user_agent}, timeout=60)
    client = RegisterClient(http, delay_s=settings.register_delay_s)

    with connect() as conn:
        if not args.skip_lookups:
            load_lookups(conn, client)
        for name in names:
            load(conn, client, BY_NAME[name], max_pages=args.max_pages)
    return 0


if __name__ == "__main__":
    sys.exit(main())
