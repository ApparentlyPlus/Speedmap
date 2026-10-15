from __future__ import annotations

from collections.abc import Iterator

import psycopg
import pytest
from psycopg.rows import TupleRow

from normalise.build import Step, discover, run

PIN_STEP = "065_address_street"
REACH_STEP = "110_street_reach"
SPEED_STEP = "120_street_speed"

TOUCHED = (
    "municipality, raw_dimos, address, raw_coverpoint, coverage, coverage_area, "
    "raw_wiredservice, raw_geo_coverage_copper, address_coverage, street, street_provider"
)

# ~500 m cabinet in Greek Grid
CABINET_2100 = (
    '{"type": "MultiPolygon", "coordinates": '
    "[[[[500000.0, 4520000.0], [500500.0, 4520000.0], "
    "[500500.0, 4520500.0], [500000.0, 4520000.0]]]]}"
)

INSIDE_LINE = "MULTILINESTRING((24.0050 40.8340, 24.0060 40.8350))"
OUTSIDE_LINE = "MULTILINESTRING((25.0000 37.0000, 25.0010 37.0010))"


def _reset(conn: psycopg.Connection[TupleRow]) -> None:
    conn.execute(f"truncate {TOUCHED} cascade")
    conn.execute("insert into provider (code, display_name, kind) values ('TEST', 'Test', 'altnet') on conflict (code) do nothing")
    conn.execute("insert into source (name, url) values ('register', 'https://example.invalid') on conflict (name) do nothing")
    conn.execute(
        "insert into municipality (id, kallikratis_code, name, geom) values "
        "(1, '0000', 'ΔΗΜΟΣ ΤΕΣΤ', %s) on conflict (id) do nothing",
        ("SRID=4326;MULTIPOLYGON(((24.0 40.8, 24.1 40.8, 24.1 40.9, 24.0 40.8)))",),
    )
    conn.commit()


@pytest.fixture
def reachable(db: psycopg.Connection[TupleRow]) -> Iterator[psycopg.Connection[TupleRow]]:
    _reset(db)
    yield db
    db.execute(f"truncate {TOUCHED} cascade")
    db.commit()


# 110 reads address.street_id, so without 065 it'd find nothing and pass
def _steps() -> list[Step]:
    wanted = {PIN_STEP, REACH_STEP, SPEED_STEP}
    return [s for s in discover() if s.name in wanted]


def _provider(conn: psycopg.Connection[TupleRow]) -> int:
    row = conn.execute("select id from provider where code = 'TEST'").fetchone()
    assert row is not None
    return int(row[0])


def _street(conn: psycopg.Connection[TupleRow], geom: str = INSIDE_LINE) -> int:
    row = conn.execute(
        "insert into street (name, name_fold, latin_key, sort_key, highway, ways, geom, "
        "municipality_id) values ('ΤΕΣΤ', 'ΤΕΣΤ', 'TEST', 'ΤΕΣΤ', 'residential', 1, %s, 1) returning id",
        (f"SRID=4326;{geom}",),
    ).fetchone()
    conn.commit()
    assert row is not None
    return int(row[0])


def _area(conn: psycopg.Connection[TupleRow], *, band: int | None = 6, family: str = "copper",
          technology: str = "VECT_VDSL", scale: float = 1.0) -> None:
    # scale blows it up past the cap into a district
    conn.execute(
        "insert into coverage_area (source, source_ref, provider_id, technology, family, "
        "speed_band_id, assertion, geom) values ('register', %s, %s, %s, %s, %s, 'declared', "
        "st_multi(st_scale(st_transform(st_setsrid(st_geomfromgeojson(%s), 2100), 4326), "
        "st_point(%s, %s), 'POINT(24.005 40.834)'::geometry))::geography)",
        (f"cab-{technology}-{scale}", _provider(conn), technology, family, band, CABINET_2100, scale, scale),
    )
    conn.commit()


def _door(conn: psycopg.Connection[TupleRow], *, band: int | None, family: str = "fiber",
          technology: str = "FTTH") -> None:
    conn.execute(
        "insert into address (street, street_fold, geom, search_key, latin_key, municipality_id) "
        "values ('ΤΕΣΤ', 'ΤΕΣΤ', 'SRID=4326;POINT(24.0055 40.8345)', 'ΤΕΣΤ', 'TEST', 1)"
    )
    conn.execute(
        "insert into address_coverage (address_id, provider_id, technology, family, "
        "matched_by, speed_band_id, built_by) select a.id, %s, %s, %s, 'point', %s, '050' "
        "from address a where a.street_fold = 'ΤΕΣΤ'",
        (_provider(conn), technology, family, band),
    )
    conn.commit()


def _built(conn: psycopg.Connection[TupleRow], *, lon: float = 24.0055, lat: float = 40.8345, prempass: int = 12,
           addressed: bool = False) -> None:
    # fiber with no street name. addressed links it to a door like 025 would
    conn.execute("update provider set builds_own_network = true, register_id = 903 where code = 'TEST'")
    conn.execute(
        "insert into raw_coverpoint (coverid, infrprov, prempass, address, point) values "
        "('built-1', 903, %s, '64007,ΤΕΣΤ, ,Δ. ΤΕΣΤ', st_setsrid(st_point(%s, %s), 4326))",
        (prempass, lon, lat),
    )
    if addressed:
        conn.execute(
            "insert into address (street, street_fold, geom, search_key, latin_key, municipality_id) "
            "values ('ΤΕΣΤ', 'ΤΕΣΤ', 'SRID=4326;POINT(24.0055 40.8345)', 'ΤΕΣΤ', 'TEST', 1)"
        )
        conn.execute(
            "insert into address_point (address_id, coverid) select a.id, 'built-1' from address a "
            "where a.street_fold = 'ΤΕΣΤ'"
        )
    conn.commit()


def _reach(conn: psycopg.Connection[TupleRow]) -> list[tuple[str, float | None]]:
    rows = conn.execute(
        "select p.code, sp.mbps from street_provider sp join provider p on p.id = sp.provider_id order by p.code"
    ).fetchall()
    return [(str(code), None if mbps is None else float(mbps)) for code, mbps in rows]


def _best(conn: psycopg.Connection[TupleRow]) -> float | None:
    row = conn.execute("select best_mbps from street").fetchone()
    assert row is not None
    return None if row[0] is None else float(row[0])


def _figure(conn: psycopg.Connection[TupleRow], band: int | None, technology: str) -> float | None:
    _reset(conn)
    _street(conn)
    _area(conn, band=band, technology=technology)
    run(conn, _steps())
    return _best(conn)


def test_routes(reachable: psycopg.Connection[TupleRow]) -> None:
    # half the streets have no door filed, the cabinet still reaches them
    _street(reachable)
    _area(reachable, band=6)
    run(reachable, _steps())
    assert _reach(reachable) == [("TEST", 100.0)]
    assert _best(reachable) == 100.0

    _reset(reachable)
    _street(reachable, OUTSIDE_LINE)
    _area(reachable, band=6)
    run(reachable, _steps())
    assert _reach(reachable) == []
    assert _best(reachable) is None

    # INALAN files 112,739 doors and no areas
    _reset(reachable)
    _street(reachable)
    _door(reachable, band=8)
    run(reachable, _steps())
    assert _reach(reachable) == [("TEST", 1000.0)]

    _reset(reachable)
    _street(reachable)
    _area(reachable, band=6)
    _door(reachable, band=8)
    run(reachable, _steps())
    assert _reach(reachable) == [("TEST", 1000.0)]
    assert _best(reachable) == 1000.0
    run(reachable, _steps())
    assert _reach(reachable) == [("TEST", 1000.0)]


def test_routes_excluded(reachable: psycopg.Connection[TupleRow]) -> None:
    # Λίμνης Κορώνειας only crosses 36.8 km2 filings
    _street(reachable)
    _area(reachable, band=6, scale=40.0)
    run(reachable, _steps())
    assert _reach(reachable) == []
    assert _best(reachable) is None
    assert reachable.execute("select cabinet_m2()").fetchone() == (5_000_000.0,)

    # 5G would put 40,775 of 40,796 streets at exactly 1000
    _reset(reachable)
    _street(reachable)
    _door(reachable, band=7, family="wireless", technology="FWA_5G")
    run(reachable, _steps())
    assert _reach(reachable) == []
    assert _best(reachable) is None


def test_withdrawn(reachable: psycopg.Connection[TupleRow]) -> None:
    street_id = _street(reachable)
    _area(reachable, band=6)
    run(reachable, _steps())
    assert _best(reachable) == 100.0

    reachable.execute("delete from coverage_area")
    reachable.commit()
    run(reachable, _steps())
    assert _reach(reachable) == []
    assert _best(reachable) is None
    assert reachable.execute("select count(*) from street where id = %s", (street_id,)).fetchone() == (1,)


def test_figures(reachable: psycopg.Connection[TupleRow]) -> None:
    # sold speed, not the register's band and not max_plausible_mbps
    assert _figure(reachable, band=6, technology="VECT_VDSL") == 100.0
    # band 3 (2-10) caps it, band 8 (>= 1000) lifts nothing
    assert _figure(reachable, band=3, technology="VECT_VDSL") == 10.0
    assert _figure(reachable, band=8, technology="VECT_VDSL") == 100.0
    # 70.8% of fiber filings have no band, least() skips nulls
    assert _figure(reachable, band=None, technology="VECT_VDSL") == 100.0
    # ADSL filed at 100-300 reached 1,061 streets
    assert _figure(reachable, band=6, technology="ADSL") == 24.0
    assert _figure(reachable, band=7, technology="VDSL") == 50.0

    sold = reachable.execute(
        "select distinct sold_mbps from technology where family in ('copper', 'fiber') and sold_mbps is not null order by 1"
    ).fetchall()
    assert [float(row[0]) for row in sold] == [24.0, 50.0, 100.0, 1000.0]


def test_figures_fiber(reachable: psycopg.Connection[TupleRow]) -> None:
    _street(reachable)
    _door(reachable, band=8, family="fiber", technology="FTTH")
    run(reachable, _steps())
    assert _best(reachable) == 1000.0

    _reset(reachable)
    _street(reachable)
    _door(reachable, band=None, family="fiber", technology="FTTH")
    run(reachable, _steps())
    assert _best(reachable) == 1000.0

    # 758,885 of 1,071,133 FTTH filings have no band
    _reset(reachable)
    _street(reachable)
    _area(reachable, band=6, technology="VECT_VDSL")
    _door(reachable, band=None, family="fiber", technology="FTTH")
    run(reachable, _steps())
    assert _best(reachable) == 1000.0

    _reset(reachable)
    _street(reachable)
    for tech in ("ADSL", "VDSL", "VECT_VDSL"):
        _area(reachable, band=None, technology=tech)
    run(reachable, _steps())
    assert _best(reachable) == 100.0


def test_built(reachable: psycopg.Connection[TupleRow]) -> None:
    # Πύλου-Νέστορος has 4,789 fiber points and 50 addresses
    _street(reachable)
    _built(reachable)
    run(reachable, _steps())
    assert _reach(reachable) == [("TEST", 1000.0)]

    # ~900 m east, past the 100 m cut
    _reset(reachable)
    _street(reachable)
    _built(reachable, lon=24.0160, lat=40.8345)
    run(reachable, _steps())
    assert _reach(reachable) == []

    # already on a door, route three leaves it alone. Drop the not exists and this is a gigabit
    _reset(reachable)
    _street(reachable)
    _built(reachable, addressed=True)
    run(reachable, _steps())
    assert _reach(reachable) == []
