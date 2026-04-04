"""
Loading the register into raw_*: upsert, resume, and projection handling.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import psycopg
import pytest
from psycopg.rows import TupleRow

from ingest.load import (
    TARGETS,
    GeometryCrsError,
    geojson_srid,
    geometry_param,
    load,
    upsert_sql,
)
from ingest.register import BY_NAME, RegisterClient
from tests.test_register_client import client_for, fake_register

PROVIDER = BY_NAME["provider"]
COPPER = BY_NAME["geo_coverage_copper"]

PROVIDERS: list[dict[str, Any]] = [
    {"id": 1, "name": "OTE", "short_name": "OTE"},
    {"id": 2, "name": "Nova", "short_name": "NOVA"},
    {"id": 3, "name": "Vodafone", "short_name": "VF"},
]


def polygon(srid: int) -> dict[str, Any]:
    return {
        "type": "MultiPolygon",
        "crs": {"type": "name", "properties": {"name": f"EPSG:{srid}"}},
        "coordinates": [
            [
                [
                    [300000.0, 4200000.0],
                    [300100.0, 4200000.0],
                    [300100.0, 4200100.0],
                    [300000.0, 4200000.0],
                ]
            ]
        ],
    }


def copper_rows(srid: int = 2100) -> list[dict[str, Any]]:
    return [
        {
            "coverid": f"c{n}",
            "servprov_ids": "1",
            "technolo_ids": "3",
            "maxdown_ids": "6",
            "ownrship_ids": "2",
            "dimos_id": "173",
            "geom": polygon(srid),
        }
        for n in range(1, 4)
    ]


def loader(rows: list[dict[str, Any]], cap: int = 500) -> RegisterClient:
    return client_for(fake_register(rows, cap=cap))


TOUCHED = "raw_provider, raw_geo_coverage_copper, register_fetch"


@pytest.fixture
def loadable(db: psycopg.Connection[TupleRow]) -> Iterator[psycopg.Connection[TupleRow]]:
    """A clean slate for tests of code that commits, which rollback cannot undo."""
    db.execute(f"truncate {TOUCHED}")
    db.commit()
    yield db
    db.execute(f"truncate {TOUCHED}")
    db.commit()


# geojson_srid


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ({"crs": {"properties": {"name": "EPSG:2100"}}}, 2100),
        ({"crs": {"properties": {"name": "EPSG:4326"}}}, 4326),
        ({"crs": {"properties": {"name": "urn:ogc:def:crs:EPSG::4326"}}}, 4326),
        ({}, None),
        ({"crs": None}, None),
        ({"crs": {"properties": {"name": "nonsense"}}}, None),
    ],
)
def test_geojson_srid(value: dict[str, Any], expected: int | None) -> None:
    assert geojson_srid(value) == expected


def test_wrong_projection_is_rejected() -> None:
    """Copper is Greek Grid; a 4326 body would silently land in the wrong hemisphere."""
    with pytest.raises(GeometryCrsError, match="expected EPSG:2100, got EPSG:4326"):
        geometry_param("geom", polygon(4326), 2100)


def test_missing_crs_is_accepted_at_the_expected_srid() -> None:
    """GeoJSON without a crs member is not wrong, it is merely unlabelled."""
    assert geometry_param("geom", {"type": "Point", "coordinates": [1, 2]}, 4326) is not None


def test_null_geometry_stays_null() -> None:
    assert geometry_param("waitpoin", None, 4326) is None


# generated sql


def test_geometry_columns_get_an_explicit_srid() -> None:
    sql = upsert_sql(TARGETS["geo_coverage_copper"], ("coverid", "geom"))
    assert "st_setsrid(st_geomfromgeojson(%s), 2100)" in sql


def test_conflict_updates_every_non_key_column() -> None:
    sql = upsert_sql(TARGETS["provider"], ("id", "name", "short_name"))
    assert (
        "on conflict (id) do update set name = excluded.name, short_name = excluded.short_name"
        in sql
    )


# loading


def test_rows_land_in_the_raw_table(loadable: psycopg.Connection[TupleRow]) -> None:
    assert load(loadable, loader(PROVIDERS), PROVIDER) == 3
    rows = loadable.execute("select id, short_name from raw_provider order by id").fetchall()
    assert rows == [(1, "OTE"), (2, "NOVA"), (3, "VF")]


def test_reloading_is_idempotent(loadable: psycopg.Connection[TupleRow]) -> None:
    load(loadable, loader(PROVIDERS), PROVIDER)
    load(loadable, loader(PROVIDERS), PROVIDER)
    row = loadable.execute("select count(*) from raw_provider").fetchone()
    assert row == (3,)


def test_reloading_refreshes_changed_values(loadable: psycopg.Connection[TupleRow]) -> None:
    load(loadable, loader(PROVIDERS), PROVIDER)
    loadable.execute("update register_fetch set last_key = null where dataset = 'provider'")
    renamed = [{**PROVIDERS[0], "name": "Cosmote"}, *PROVIDERS[1:]]
    load(loadable, loader(renamed), PROVIDER)
    row = loadable.execute("select name from raw_provider where id = 1").fetchone()
    assert row == ("Cosmote",)


def test_progress_is_recorded_for_resume(loadable: psycopg.Connection[TupleRow]) -> None:
    load(loadable, loader(PROVIDERS), PROVIDER)
    row = loadable.execute(
        "select last_key, fetched, total from register_fetch where dataset = 'provider'"
    ).fetchone()
    assert row == ("3", 3, 3)


def test_an_interrupted_run_resumes_where_it_stopped(
    loadable: psycopg.Connection[TupleRow],
) -> None:
    """One page at a time, then continue: no row is fetched twice and none is skipped."""
    load(loadable, loader(PROVIDERS, cap=1), PROVIDER, max_pages=1)
    first = loadable.execute("select count(*) from raw_provider").fetchone()
    assert first == (1,)

    load(loadable, loader(PROVIDERS, cap=1), PROVIDER, max_pages=1)
    resumed = loadable.execute("select id from raw_provider order by id").fetchall()
    assert resumed == [(1,), (2,)]


def test_projected_geometry_keeps_its_srid(loadable: psycopg.Connection[TupleRow]) -> None:
    load(loadable, loader(copper_rows()), COPPER)
    row = loadable.execute(
        "select st_srid(geom), st_geometrytype(geom) from raw_geo_coverage_copper limit 1"
    ).fetchone()
    assert row == (2100, "ST_MultiPolygon")


def test_a_reprojected_register_stops_the_load(loadable: psycopg.Connection[TupleRow]) -> None:
    with pytest.raises(GeometryCrsError):
        load(loadable, loader(copper_rows(srid=4326)), COPPER)
