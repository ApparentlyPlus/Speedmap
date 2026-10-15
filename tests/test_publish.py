from __future__ import annotations

import gzip
import json
import math
import pathlib
from typing import Any

import psycopg
import pytest
from psycopg.rows import TupleRow

from publish import features, fields

STREET = (
    "insert into street (name, name_fold, latin_key, sort_key, highway, ways, geom) "
    "values ('ΤΕΣΤ', 'ΤΕΣΤ', 'TEST', 'ΤΕΣΤ', 'residential', 1, "
    "'SRID=4326;MULTILINESTRING((23.0 40.7, 23.01 40.71))') returning id"
)

CELL = (
    "insert into speed_cell (quadkey, family, observed_on, avg_down_mbps, avg_up_mbps, "
    "latency_ms, tests, devices, geom) values ('1202332311322301', 'fixed', '2026-01-01', "
    "120.5, 20.25, 14, 7, 5, 'SRID=4326;POINT(23.0 40.7)')"
)

# cells are clipped to the municipalities, without one it's at sea
MUNICIPALITY = (
    "insert into municipality (id, name, geom) values (1, 'ΤΕΣΤ', "
    "'SRID=4326;MULTIPOLYGON(((22.9 40.6, 23.1 40.6, 23.1 40.8, 22.9 40.8, 22.9 40.6)))')"
)


@pytest.fixture
def drawn(seeded: psycopg.Connection[TupleRow]) -> psycopg.Connection[TupleRow]:
    row = seeded.execute(STREET).fetchone()
    assert row is not None
    seeded.execute(
        "insert into street_provider (street_id, provider_id, mbps) values "
        "(%s, (select id from provider where code = 'TEST'), 300)",
        (row[0],),
    )
    seeded.execute("update street set best_mbps = 300 where id = %s", (row[0],))
    seeded.execute(MUNICIPALITY)
    seeded.execute(CELL)
    return seeded


Feature = dict[str, Any]


def _read(path: pathlib.Path) -> list[Feature]:
    parsed: list[Feature] = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    return parsed


def test_streets(drawn: psycopg.Connection[TupleRow], tmp_path: pathlib.Path) -> None:
    features.streets(drawn, tmp_path / "streets.geojsonl")
    written = _read(tmp_path / "streets.geojsonl")
    assert len(written) == 1
    assert set(written[0]["properties"]) == set(fields.STREETS_FIELDS)
    props = written[0]["properties"]
    assert props["nprov"] == 1
    # reaches it with no speed is the commonest case, a 0 would paint it slowest
    assert props[fields.STREETS_BY_PROVIDER["NOVA"]] is None

    features.streets_overview(drawn, tmp_path / "overview.geojsonl")
    written = _read(tmp_path / "overview.geojsonl")
    assert len(written) == 1
    assert set(written[0]["properties"]) == set(fields.STREETS_FIELDS) - {"id", "nprov"}
    assert written[0]["tippecanoe"] == {"maxzoom": features.DETAIL_FROM - 1}

    # no zoom without streets
    detail = _read(tmp_path / "streets.geojsonl")[0]["tippecanoe"]["minzoom"]
    overview = _read(tmp_path / "overview.geojsonl")[0]["tippecanoe"]["maxzoom"]
    assert detail == overview + 1

    row = drawn.execute("select id from street limit 1").fetchone()
    assert row is not None
    drawn.execute(
        "insert into street_provider (street_id, provider_id, mbps) values "
        "(%s, (select id from provider where code = 'TELEKOM'), 1000)",
        (row[0],),
    )
    features.streets(drawn, tmp_path / "streets.geojsonl")
    assert _read(tmp_path / "streets.geojsonl")[0]["properties"][fields.STREETS_BY_PROVIDER["TELEKOM"]] == 1000


def test_streets_overview_order(drawn: psycopg.Connection[TupleRow], tmp_path: pathlib.Path) -> None:
    # tippecanoe only merges neighbours
    for name in ("ΑΛΦΑ", "ΒΗΤΑ", "ΓΑΜΑ"):
        drawn.execute(
            "insert into street (name, name_fold, latin_key, sort_key, highway, ways, geom, "
            "best_mbps) values (%s, %s, %s, %s, 'residential', 1, "
            "'SRID=4326;MULTILINESTRING((23.0 40.7, 23.01 40.71))', 24)",
            (name, name, name, name),
        )
    features.streets_overview(drawn, tmp_path / "overview.geojsonl")
    speeds = [f["properties"]["best_mbps"] for f in _read(tmp_path / "overview.geojsonl")]
    assert speeds == sorted(speeds)


def test_cells(drawn: psycopg.Connection[TupleRow], tmp_path: pathlib.Path) -> None:
    features.cells(drawn, tmp_path / "cells.geojsonl")
    written = _read(tmp_path / "cells.geojsonl")
    assert len(written) == 1
    assert set(written[0]["properties"]) == set(fields.CELLS_FIELDS)

    # the square that was measured, not Ookla's centroid
    square = written[0]["geometry"]
    assert square["type"] == "Polygon"
    corners = square["coordinates"][0]
    across = drawn.execute(
        "select st_distance(st_setsrid(st_point(%s, %s), 4326)::geography, st_setsrid(st_point(%s, %s), 4326)::geography)",
        (*corners[0], *corners[2]),
    ).fetchone()
    assert across is not None
    expected = features.HALF_TILE * 2 * math.cos(math.radians(40.7)) * math.sqrt(2)
    assert expected * 0.98 < float(across[0]) < expected * 1.02


def test_outline(drawn: psycopg.Connection[TupleRow], tmp_path: pathlib.Path) -> None:
    features.outline(drawn, tmp_path / "greece.json")
    plain = (tmp_path / "greece.json").read_bytes()
    assert gzip.decompress((tmp_path / "greece.json.gz").read_bytes()) == plain


def test_write_atomic(drawn: psycopg.Connection[TupleRow], tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # open maps are reading the old one
    out = tmp_path / "streets.geojsonl"
    out.write_text('{"kept": true}\n', encoding="utf-8")
    monkeypatch.setattr(features, "STREETS", "select bad_sql_here")
    with pytest.raises(psycopg.errors.UndefinedColumn):
        features.streets(drawn, out)
    assert out.read_text(encoding="utf-8") == '{"kept": true}\n'
    assert list(tmp_path.glob("streets.geojsonl.*")) == []
