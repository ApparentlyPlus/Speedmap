"""Load the register into the raw_* tables. Every page is committed with its resume key."""

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
    pass


@dataclass(frozen=True)
class Target:
    table: str
    keys: tuple[str, ...]
    geometry: Mapping[str, int] = field(default_factory=dict)  # column -> SRID


TARGETS: dict[str, Target] = {
    "provider": Target("raw_provider", ("id",)),
    "dimos": Target("raw_dimos", ("gid",), {"geom": 2100, "geom4326": 4326}),
    "wireless_cell": Target("raw_wireless_cell", ("uniqueid",), {"geom": 2100}),
    "wireless": Target("raw_wireless_grid", ("id",)),
    "coverpoint": Target("raw_coverpoint", ("coverid",), {"point": 4326, "waitpoin": 4326}),
    "wiredservice": Target("raw_wiredservice", ("id",)),
    "coverage_ftth": Target("raw_coverage_ftth", ("id",), {"geom": 4326}),
    "coverage_copper": Target("raw_coverage_copper", ("id",), {"geom": 2100}),
    "geo_coverage_copper": Target("raw_geo_coverage_copper", ("coverid",), {"geom": 2100}),
}


def geojson_srid(value: Mapping[str, Any]) -> int | None:
    crs = value.get("crs")
    if not isinstance(crs, Mapping):
        return None
    props = crs.get("properties")
    if not isinstance(props, Mapping):
        return None
    code = str(props.get("name", "")).rpartition(":")[2]
    return int(code) if code.isdigit() else None


def geometry_param(column: str, value: object, expected: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise GeometryCrsError(f"{column}: expected GeoJSON, got {type(value).__name__}")
    srid = geojson_srid(value)
    if srid is not None and srid != expected:
        raise GeometryCrsError(f"{column}: expected EPSG:{expected}, got EPSG:{srid}")
    return json.dumps(value)


def upsert_sql(target: Target, columns: tuple[str, ...]) -> str:
    placeholders = [
        f"st_setsrid(st_geomfromgeojson(%s), {target.geometry[c]})" if c in target.geometry else "%s"
        for c in columns
    ]
    rest = [c for c in columns if c not in target.keys]
    action = "update set " + ", ".join(f"{c} = excluded.{c}" for c in rest) if rest else "nothing"
    return (
        f"insert into {target.table} ({', '.join(columns)}) "
        f"values ({', '.join(placeholders)}) "
        f"on conflict ({', '.join(target.keys)}) do {action}"
    )


def write_page(conn: psycopg.Connection[TupleRow], target: Target, rows: Iterable[Row]) -> int:
    batch = list(rows)
    if not batch:
        return 0
    cols = tuple(batch[0])
    params = [
        tuple(geometry_param(c, r[c], target.geometry[c]) if c in target.geometry else r[c] for c in cols)
        for r in batch
    ]
    conn.cursor().executemany(upsert_sql(target, cols), params)
    return len(batch)


def load(conn: psycopg.Connection[TupleRow], client: RegisterClient, dataset: Dataset, *,
         max_pages: int | None = None) -> int:
    name = dataset.name
    target = TARGETS[name]
    total = client.count(dataset)
    cap = client.page_cap(dataset)
    conn.execute(
        "insert into register_fetch (dataset, run_started_at) values (%s, now()) "
        "on conflict (dataset) do update set run_started_at = now(), run_fetched = 0",
        (name,),
    )
    row = conn.execute("select last_key from register_fetch where dataset = %s", (name,)).fetchone()
    after = None if row is None else row[0]
    conn.commit()

    loaded = 0
    for i, page in enumerate(client.pages(dataset, cap=cap, after=after), start=1):
        loaded += write_page(conn, target, page)
        conn.execute(
            "update register_fetch set last_key = %s, fetched = fetched + %s, "
            "run_fetched = run_fetched + %s, total = coalesce(%s, total), "
            "updated_at = now() where dataset = %s",
            (str(page[-1][dataset.key]), len(page), len(page), total, name),
        )
        conn.commit()
        print(f"  {name}: {loaded} rows", end="\r", file=sys.stderr)
        if max_pages is not None and i >= max_pages:
            break
    else:
        # the resume key is only for interrupted runs, a full one starts over next time
        conn.execute("update register_fetch set last_key = null where dataset = %s", (name,))
        conn.commit()

    print(f"\r  {name}: {loaded} rows loaded ")
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
