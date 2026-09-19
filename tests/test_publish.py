"""The tile layers: exactly the fields the contract names, and nothing half written."""

from __future__ import annotations

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

# The cells are clipped to the country, and the municipalities are what the country is made
# of, so a cell with no municipality under it is a cell in the sea off Albania.
MUNICIPALITY = (
    "insert into municipality (id, name, geom) values (1, 'ΤΕΣΤ', "
    "'SRID=4326;MULTIPOLYGON(((22.9 40.6, 23.1 40.6, 23.1 40.8, 22.9 40.8, 22.9 40.6)))')"
)


@pytest.fixture
def drawn(seeded: psycopg.Connection[TupleRow]) -> psycopg.Connection[TupleRow]:
    """One street an operator reaches at a known speed, and one measured cell in Greece."""
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


# A GeoJSON feature is nested and heterogeneous. Typing it precisely here would describe
# the format rather than test the layer.
Feature = dict[str, Any]


def read(path: pathlib.Path) -> list[Feature]:
    parsed: list[Feature] = [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
    ]
    return parsed


def test_a_street_carries_exactly_the_fields_the_contract_names(
    drawn: psycopg.Connection[TupleRow], tmp_path: pathlib.Path
) -> None:
    """A field the builder stopped writing is undefined in the renderer and silent."""
    features.streets(drawn, tmp_path / "streets.geojsonl")
    written = read(tmp_path / "streets.geojsonl")
    assert len(written) == 1
    assert set(written[0]["properties"]) == set(fields.STREETS_FIELDS)


def test_a_cell_carries_exactly_the_fields_the_contract_names(
    drawn: psycopg.Connection[TupleRow], tmp_path: pathlib.Path
) -> None:
    features.cells(drawn, tmp_path / "cells.geojsonl")
    written = read(tmp_path / "cells.geojsonl")
    assert len(written) == 1
    assert set(written[0]["properties"]) == set(fields.CELLS_FIELDS)


def test_a_cell_is_drawn_as_the_square_that_was_measured(
    drawn: psycopg.Connection[TupleRow], tmp_path: pathlib.Path
) -> None:
    """Ookla publish a centroid. What was measured is a tile. As a point it becomes a dot

    whose size means nothing, and a tested street looks like a tested suburb.
    """
    features.cells(drawn, tmp_path / "cells.geojsonl")
    drawn_cell = read(tmp_path / "cells.geojsonl")[0]["geometry"]
    assert drawn_cell["type"] == "Polygon"
    corners = drawn_cell["coordinates"][0]
    across = drawn.execute(
        "select st_distance("
        "  st_setsrid(st_point(%s, %s), 4326)::geography,"
        "  st_setsrid(st_point(%s, %s), 4326)::geography)",
        (*corners[0], *corners[2]),
    ).fetchone()
    assert across is not None
    expected = features.HALF_TILE * 2 * math.cos(math.radians(40.7)) * math.sqrt(2)
    assert expected * 0.98 < float(across[0]) < expected * 1.02


def test_an_operator_speed_lands_under_its_own_field(
    drawn: psycopg.Connection[TupleRow], tmp_path: pathlib.Path
) -> None:
    """Two operators sharing a field is one operator's speed under both names."""
    row = drawn.execute("select id from street limit 1").fetchone()
    assert row is not None
    drawn.execute(
        "insert into street_provider (street_id, provider_id, mbps) values "
        "(%s, (select id from provider where code = 'OTE'), 1000)",
        (row[0],),
    )
    features.streets(drawn, tmp_path / "streets.geojsonl")
    written = read(tmp_path / "streets.geojsonl")[0]["properties"]
    assert written[fields.STREETS_BY_PROVIDER["OTE"]] == 1000


def test_an_operator_with_no_filed_speed_is_null_and_not_zero(
    drawn: psycopg.Connection[TupleRow], tmp_path: pathlib.Path
) -> None:
    """Serves this street, files no speed is the commonest state in the register, and a
    zero would paint it as the slowest thing on the map."""
    features.streets(drawn, tmp_path / "streets.geojsonl")
    written = read(tmp_path / "streets.geojsonl")[0]["properties"]
    assert written[fields.STREETS_BY_PROVIDER["NOVA"]] is None


def test_the_operator_count_counts_operators(
    drawn: psycopg.Connection[TupleRow], tmp_path: pathlib.Path
) -> None:
    features.streets(drawn, tmp_path / "streets.geojsonl")
    written = read(tmp_path / "streets.geojsonl")[0]["properties"]
    assert written["nprov"] == 1


def test_a_layer_is_named_only_once_it_is_whole(
    drawn: psycopg.Connection[TupleRow], tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A build that dies half way must leave the previous layer alone: it is being read by
    every open map at the time."""
    out = tmp_path / "streets.geojsonl"
    out.write_text('{"kept": true}\n', encoding="utf-8")

    def explode(*_: object, **__: object) -> None:
        raise RuntimeError("tippecanoe went away")

    monkeypatch.setattr(features, "STREETS", "select bad_sql_here")
    with pytest.raises(psycopg.errors.UndefinedColumn):
        features.streets(drawn, out)

    assert out.read_text(encoding="utf-8") == '{"kept": true}\n'
    assert list(tmp_path.glob("streets.geojsonl.*")) == []
