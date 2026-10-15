from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import psycopg
import pytest
from psycopg.rows import TupleRow

from ingest.load import TARGETS, GeometryCrsError, geojson_srid, geometry_param, load, upsert_sql
from ingest.register import BY_NAME, RegisterClient
from tests.test_register_client import client_for, fake_register

PROVIDER = BY_NAME["provider"]
COPPER = BY_NAME["geo_coverage_copper"]

PROVIDERS: list[dict[str, Any]] = [
    {"id": 1, "name": "TELEKOM", "short_name": "TELEKOM"},
    {"id": 2, "name": "Nova", "short_name": "NOVA"},
    {"id": 3, "name": "Vodafone", "short_name": "VF"},
]
RENAMED = [{**PROVIDERS[0], "name": "Cosmote"}, *PROVIDERS[1:]]

TOUCHED = "raw_provider, raw_geo_coverage_copper, register_fetch"


def _polygon(srid: int) -> dict[str, Any]:
    return {
        "type": "MultiPolygon",
        "crs": {"type": "name", "properties": {"name": f"EPSG:{srid}"}},
        "coordinates": [[[[300000.0, 4200000.0], [300100.0, 4200000.0], [300100.0, 4200100.0], [300000.0, 4200000.0]]]],
    }


def _copper(srid: int = 2100) -> list[dict[str, Any]]:
    return [
        {"coverid": f"c{n}", "servprov_ids": "1", "technolo_ids": "3", "maxdown_ids": "6", "ownrship_ids": "2",
         "dimos_id": "173", "geom": _polygon(srid)}
        for n in range(1, 4)
    ]


def _loader(rows: list[dict[str, Any]], cap: int = 500) -> RegisterClient:
    return client_for(fake_register(rows, cap=cap))


def _reset(conn: psycopg.Connection[TupleRow]) -> None:
    conn.execute(f"truncate {TOUCHED}")
    conn.commit()


def _progress(conn: psycopg.Connection[TupleRow], dataset: str = "provider") -> tuple[int, int, bool]:
    row = conn.execute(
        "select fetched, run_fetched, run_started_at is not null from register_fetch where dataset = %s",
        (dataset,),
    ).fetchone()
    assert row is not None
    return int(row[0]), int(row[1]), bool(row[2])


# load() commits, so truncate instead of rolling back
@pytest.fixture
def loadable(db: psycopg.Connection[TupleRow]) -> Iterator[psycopg.Connection[TupleRow]]:
    _reset(db)
    yield db
    _reset(db)


def test_geojson_srid() -> None:
    cases: list[tuple[dict[str, Any], int | None]] = [
        ({"crs": {"properties": {"name": "EPSG:2100"}}}, 2100),
        ({"crs": {"properties": {"name": "EPSG:4326"}}}, 4326),
        ({"crs": {"properties": {"name": "urn:ogc:def:crs:EPSG::4326"}}}, 4326),
        ({}, None),
        ({"crs": None}, None),
        ({"crs": {"properties": {"name": "nonsense"}}}, None),
    ]
    for value, expected in cases:
        assert geojson_srid(value) == expected

    # copper is Greek Grid, 4326 would land in the wrong hemisphere
    with pytest.raises(GeometryCrsError, match="expected EPSG:2100, got EPSG:4326"):
        geometry_param("geom", _polygon(4326), 2100)
    assert geometry_param("geom", {"type": "Point", "coordinates": [1, 2]}, 4326) is not None
    assert geometry_param("waitpoin", None, 4326) is None


def test_upsert_sql() -> None:
    sql = upsert_sql(TARGETS["geo_coverage_copper"], ("coverid", "geom"))
    assert "st_setsrid(st_geomfromgeojson(%s), 2100)" in sql
    sql = upsert_sql(TARGETS["provider"], ("id", "name", "short_name"))
    assert ("on conflict (id) do update set name = excluded.name, short_name = excluded.short_name" in sql)


def test_load(loadable: psycopg.Connection[TupleRow]) -> None:
    assert load(loadable, _loader(PROVIDERS), PROVIDER) == 3
    rows = loadable.execute("select id, short_name from raw_provider order by id").fetchall()
    assert rows == [(1, "TELEKOM"), (2, "NOVA"), (3, "VF")]

    load(loadable, _loader(PROVIDERS), PROVIDER)
    assert loadable.execute("select count(*) from raw_provider").fetchone() == (3,)

    _reset(loadable)
    load(loadable, _loader(PROVIDERS), PROVIDER)
    loadable.execute("update register_fetch set last_key = null where dataset = 'provider'")
    load(loadable, _loader(RENAMED), PROVIDER)
    assert loadable.execute("select name from raw_provider where id = 1").fetchone() == ("Cosmote",)

    # a finished run starts the next one from the top
    _reset(loadable)
    load(loadable, _loader(PROVIDERS), PROVIDER)
    load(loadable, _loader(RENAMED), PROVIDER)
    assert loadable.execute("select name from raw_provider where id = 1").fetchone() == ("Cosmote",)


def test_load_resume(loadable: psycopg.Connection[TupleRow]) -> None:
    load(loadable, _loader(PROVIDERS, cap=1), PROVIDER, max_pages=2)
    row = loadable.execute("select last_key, fetched, total from register_fetch where dataset = 'provider'").fetchone()
    assert row == ("2", 2, 3)

    _reset(loadable)
    load(loadable, _loader(PROVIDERS, cap=1), PROVIDER, max_pages=1)
    assert loadable.execute("select count(*) from raw_provider").fetchone() == (1,)
    load(loadable, _loader(PROVIDERS, cap=1), PROVIDER, max_pages=1)
    assert loadable.execute("select id from raw_provider order by id").fetchall() == [(1,), (2,)]


def test_load_geometry(loadable: psycopg.Connection[TupleRow]) -> None:
    load(loadable, _loader(_copper()), COPPER)
    row = loadable.execute("select st_srid(geom), st_geometrytype(geom) from raw_geo_coverage_copper limit 1").fetchone()
    assert row == (2100, "ST_MultiPolygon")

    with pytest.raises(GeometryCrsError):
        load(loadable, _loader(_copper(srid=4326)), COPPER)


def test_load_progress(loadable: psycopg.Connection[TupleRow]) -> None:
    load(loadable, _loader(PROVIDERS), PROVIDER)
    row = loadable.execute("select created_at <= run_started_at from register_fetch where dataset = 'provider'").fetchone()
    assert row == (True,)
    assert _progress(loadable) == (3, 3, True)
    row = loadable.execute("select fetched, total, pct from register_progress where dataset = 'provider'").fetchone()
    assert row is not None
    assert row[0] == 3
    assert row[1] == 3
    assert float(row[2]) == 100.0

    # fetched is cumulative, run_fetched resets
    first = loadable.execute("select run_started_at from register_fetch where dataset = 'provider'").fetchone()
    loadable.execute("update register_fetch set last_key = null where dataset = 'provider'")
    loadable.commit()
    load(loadable, _loader(PROVIDERS), PROVIDER)
    fetched, run_fetched, started = _progress(loadable)
    assert fetched == 6
    assert run_fetched == 3
    assert started
    second = loadable.execute("select run_started_at from register_fetch where dataset = 'provider'").fetchone()
    assert first is not None and second is not None
    assert second[0] >= first[0]

    # never ran, the view mustn't divide by null
    loadable.execute("insert into register_fetch (dataset) values ('never')")
    loadable.commit()
    row = loadable.execute("select pct, rows_per_min, eta from register_progress where dataset = 'never'").fetchone()
    assert row == (None, None, None)
