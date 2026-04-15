"""The derived-table build steps, which are re-runnable rather than once-only."""

from __future__ import annotations

from collections.abc import Iterator

import psycopg
import pytest
from psycopg.rows import TupleRow

from normalise.build import Step, discover, run

ADDRESS_STEP = "020_address"
COVERAGE_STEP = "030_coverage"
AREA_STEP = "040_coverage_area"

TOUCHED = (
    "municipality, raw_dimos, address, raw_coverpoint, coverage, coverage_area, "
    "raw_wiredservice, raw_geo_coverage_copper"
)

# ΔΗΜΟΣ ΠΑΓΓΑΙΟΥ, simplified to a triangle. Only the projection and the copy are under test.
POLYGON = (
    '{"type": "MultiPolygon", "coordinates": '
    "[[[[24.0, 40.8], [24.1, 40.8], [24.1, 40.9], [24.0, 40.8]]]]}"
)


@pytest.fixture
def buildable(db: psycopg.Connection[TupleRow]) -> Iterator[psycopg.Connection[TupleRow]]:
    db.execute(f"truncate {TOUCHED} cascade")
    db.commit()
    yield db
    db.execute(f"truncate {TOUCHED} cascade")
    db.commit()


def seed_dimos(conn: psycopg.Connection[TupleRow], gid: int = 1, name: str = "ΔΗΜΟΣ ΠΑΓΓΑΙΟΥ") -> None:
    conn.execute(
        "insert into raw_dimos (gid, kalcode4, d1, geom4326) "
        "values (%s, '0503', %s, st_setsrid(st_geomfromgeojson(%s), 4326))",
        (gid, name, POLYGON),
    )
    conn.commit()


def municipality_step() -> list[Step]:
    return [s for s in discover() if s.name == "010_municipality"]


def test_steps_run_in_filename_order() -> None:
    names = [s.name for s in discover()]
    assert names == sorted(names)


def test_municipality_is_copied_from_raw(buildable: psycopg.Connection[TupleRow]) -> None:
    seed_dimos(buildable)
    run(buildable, municipality_step())
    row = buildable.execute("select id, kallikratis_code, name from municipality").fetchone()
    assert row == (1, "0503", "ΔΗΜΟΣ ΠΑΓΓΑΙΟΥ")


def test_the_step_is_re_runnable(buildable: psycopg.Connection[TupleRow]) -> None:
    """A step runs again after every register pull, so it must not accumulate rows."""
    seed_dimos(buildable)
    run(buildable, municipality_step())
    run(buildable, municipality_step())
    row = buildable.execute("select count(*) from municipality").fetchone()
    assert row == (1,)


def test_a_renamed_municipality_is_refreshed(buildable: psycopg.Connection[TupleRow]) -> None:
    seed_dimos(buildable)
    run(buildable, municipality_step())
    buildable.execute("update raw_dimos set d1 = 'ΔΗΜΟΣ ΑΛΛΟΣ' where gid = 1")
    buildable.commit()
    run(buildable, municipality_step())
    row = buildable.execute("select name from municipality").fetchone()
    assert row == ("ΔΗΜΟΣ ΑΛΛΟΣ",)


def test_geometry_becomes_geography(buildable: psycopg.Connection[TupleRow]) -> None:
    """Later joins are distance and containment on a sphere, not on a plane."""
    seed_dimos(buildable)
    run(buildable, municipality_step())
    row = buildable.execute(
        "select udt_name from information_schema.columns "
        "where table_name = 'municipality' and column_name = 'geom'"
    ).fetchone()
    assert row == ("geography",)


def test_a_point_inside_resolves_to_its_municipality(
    buildable: psycopg.Connection[TupleRow],
) -> None:
    seed_dimos(buildable)
    run(buildable, municipality_step())
    row = buildable.execute(
        "select name from municipality where st_intersects(geom, st_point(24.05, 40.83)::geography)"
    ).fetchone()
    assert row == ("ΔΗΜΟΣ ΠΑΓΓΑΙΟΥ",)


def test_a_point_outside_resolves_to_nothing(buildable: psycopg.Connection[TupleRow]) -> None:
    """Unplaced is a real answer; the nearest municipality would be a guess."""
    seed_dimos(buildable)
    run(buildable, municipality_step())
    row = buildable.execute(
        "select count(*) from municipality where st_intersects(geom, st_point(25.0, 37.0)::geography)"
    ).fetchone()
    assert row == (0,)


def address_step() -> list[Step]:
    return [s for s in discover() if s.name == ADDRESS_STEP]


def seed_point(
    conn: psycopg.Connection[TupleRow],
    coverid: str,
    address: str,
    *,
    lon: float = 24.05,
    lat: float = 40.83,
    prempass: int | None = 4,
    connstat: int | None = 1,
    vhcn: int | None = 1,
) -> None:
    conn.execute(
        "insert into raw_coverpoint (coverid, address, prempass, connstat, vhcn, point) "
        "values (%s, %s, %s, %s, %s, st_setsrid(st_point(%s, %s), 4326))",
        (coverid, address, prempass, connstat, vhcn, lon, lat),
    )
    conn.commit()


def build_addresses(conn: psycopg.Connection[TupleRow]) -> int:
    seed_dimos(conn)
    run(conn, municipality_step())
    return run(conn, address_step())[ADDRESS_STEP]


def test_a_point_becomes_an_address(buildable: psycopg.Connection[TupleRow]) -> None:
    seed_point(buildable, "a", "56429,Αμυγδαλιάς,11,ΕΥΚΑΡΠΙΑ")
    assert build_addresses(buildable) == 1
    row = buildable.execute(
        "select postcode, street, street_no, locality, premises from address"
    ).fetchone()
    assert row == ("56429", "Αμυγδαλιάς", "11", "ΕΥΚΑΡΠΙΑ", 4)


def test_a_corner_point_becomes_two_addresses(buildable: psycopg.Connection[TupleRow]) -> None:
    """6.43% of points carry two; both must be findable, and they share one geometry."""
    seed_point(buildable, "a", "26332,ΠΑΡΟΔΟΣ ΑΝΑΓΝΩΣΤΟΥ,10,Δ. ΠΑΤΡΕΩΝ|26332,ΑΝΑΓΝΩΣΤΟΥ,10,Δ. ΠΑΤΡΕΩΝ")
    assert build_addresses(buildable) == 2
    rows = buildable.execute("select street from address order by street").fetchall()
    assert [r[0] for r in rows] == ["ΑΝΑΓΝΩΣΤΟΥ", "ΠΑΡΟΔΟΣ ΑΝΑΓΝΩΣΤΟΥ"]


def test_the_same_address_on_two_points_collapses(buildable: psycopg.Connection[TupleRow]) -> None:
    """on conflict cannot touch one row twice in a statement, so the merge must deduplicate."""
    seed_point(buildable, "a", "56429,Αμυγδαλιάς,11,ΕΥΚΑΡΠΙΑ", prempass=4)
    seed_point(buildable, "b", "56429,Αμυγδαλιάς,11,ΕΥΚΑΡΠΙΑ", prempass=9)
    assert build_addresses(buildable) == 1
    row = buildable.execute("select premises from address").fetchone()
    assert row == (9,)


def test_the_municipality_is_resolved_from_the_point(
    buildable: psycopg.Connection[TupleRow],
) -> None:
    """The filed locality is ΕΥΚΑΡΠΙΑ; the municipality comes from the geometry."""
    seed_point(buildable, "a", "56429,Αμυγδαλιάς,11,ΕΥΚΑΡΠΙΑ")
    build_addresses(buildable)
    row = buildable.execute(
        "select a.locality, m.name from address a join municipality m on m.id = a.municipality_id"
    ).fetchone()
    assert row == ("ΕΥΚΑΡΠΙΑ", "ΔΗΜΟΣ ΠΑΓΓΑΙΟΥ")


def test_a_point_outside_every_municipality_still_gets_an_address(
    buildable: psycopg.Connection[TupleRow],
) -> None:
    """Unplaced is not unusable: the address is still searchable, just not attributed."""
    seed_point(buildable, "a", "56429,Αμυγδαλιάς,11,ΕΥΚΑΡΠΙΑ", lon=25.0, lat=37.0)
    assert build_addresses(buildable) == 1
    row = buildable.execute("select municipality_id from address").fetchone()
    assert row == (None,)


def test_absent_flags_stay_absent(buildable: psycopg.Connection[TupleRow]) -> None:
    """A missing connstat is unknown, not 'not connected'."""
    seed_point(buildable, "a", "56429,Αμυγδαλιάς,11,ΕΥΚΑΡΠΙΑ", prempass=None, connstat=None, vhcn=None)
    build_addresses(buildable)
    row = buildable.execute("select premises, connected, vhcn from address").fetchone()
    assert row == (None, None, None)


def test_a_zero_flag_is_false_not_absent(buildable: psycopg.Connection[TupleRow]) -> None:
    seed_point(buildable, "a", "56429,Αμυγδαλιάς,11,ΕΥΚΑΡΠΙΑ", connstat=0)
    build_addresses(buildable)
    row = buildable.execute("select connected from address").fetchone()
    assert row == (False,)


def test_a_point_with_no_street_yields_no_address(buildable: psycopg.Connection[TupleRow]) -> None:
    seed_point(buildable, "a", "56431,,1,ΣΤΑΥΡΟΥΠΟΛΗ")
    assert build_addresses(buildable) == 0


def test_rebuilding_refreshes_rather_than_duplicates(
    buildable: psycopg.Connection[TupleRow],
) -> None:
    seed_point(buildable, "a", "56429,Αμυγδαλιάς,11,ΕΥΚΑΡΠΙΑ")
    build_addresses(buildable)
    buildable.execute("update raw_coverpoint set prempass = 12 where coverid = 'a'")
    buildable.commit()
    run(buildable, address_step())
    row = buildable.execute("select count(*), max(premises) from address").fetchone()
    assert row == (1, 12)


def test_search_key_is_populated_for_type_ahead(buildable: psycopg.Connection[TupleRow]) -> None:
    seed_point(buildable, "a", "15123,ΛΕΩΦΟΡΟΣ ΙΩΑΝΝΗ ΚΑΠΟΔΙΣΤΡΙΟΥ,18,Δ. ΑΜΑΡΟΥΣΙΟΥ")
    build_addresses(buildable)
    row = buildable.execute("select search_key from address").fetchone()
    assert row == ("ΙΩΑΝΝΗ ΚΑΠΟΔΙΣΤΡΙΟΥ ΑΜΑΡΟΥΣΙΟΥ",)


def coverage_step() -> list[Step]:
    return [s for s in discover() if s.name == COVERAGE_STEP]


def seed_service(
    conn: psycopg.Connection[TupleRow],
    service_id: int,
    coverid: str,
    *,
    servprov: int = 19,
    infrprov: int = 1,
    technolo: int = 4,
    maxdown: int | None = None,
    servstar: str | None = "2026-01-01",
) -> None:
    conn.execute(
        "insert into raw_wiredservice (id, coverid, servprov, infrprov, technolo, maxdown, servstar) "
        "values (%s, %s, %s, %s, %s, %s, %s)",
        (service_id, coverid, servprov, infrprov, technolo, maxdown, servstar),
    )
    conn.commit()


def test_a_filed_service_becomes_coverage(buildable: psycopg.Connection[TupleRow]) -> None:
    seed_point(buildable, "c1", "56429,Αμυγδαλιάς,11,ΕΥΚΑΡΠΙΑ")
    seed_service(buildable, 1, "c1", maxdown=8)
    assert run(buildable, coverage_step())[COVERAGE_STEP] == 1
    row = buildable.execute(
        "select c.source, sp.code, ip.code, c.technology, c.family, sb.label, c.assertion::text "
        "from coverage c join provider sp on sp.id = c.provider_id "
        "join provider ip on ip.id = c.infra_provider_id "
        "join speed_band sb on sb.id = c.speed_band_id"
    ).fetchone()
    assert row == ("register", "METADOSIS", "OTE", "FTTH", "fibre", ">= 1000 Mbps", "declared")


def test_a_service_filed_without_a_speed_has_no_band(
    buildable: psycopg.Connection[TupleRow],
) -> None:
    """73.3% of filed services carry no band. Null is the answer, never a slow band."""
    seed_point(buildable, "c1", "56429,Αμυγδαλιάς,11,ΕΥΚΑΡΠΙΑ")
    seed_service(buildable, 1, "c1", maxdown=None)
    run(buildable, coverage_step())
    row = buildable.execute("select speed_band_id from coverage").fetchone()
    assert row == (None,)


def test_geometry_comes_from_the_infrastructure_point(
    buildable: psycopg.Connection[TupleRow],
) -> None:
    seed_point(buildable, "c1", "56429,Αμυγδαλιάς,11,ΕΥΚΑΡΠΙΑ", lon=24.05, lat=40.83)
    seed_service(buildable, 1, "c1")
    run(buildable, coverage_step())
    row = buildable.execute(
        "select round(st_x(geom::geometry)::numeric, 2) from coverage"
    ).fetchone()
    assert row is not None
    assert float(row[0]) == 24.05


def test_a_service_with_no_point_still_becomes_coverage(
    buildable: psycopg.Connection[TupleRow],
) -> None:
    """Real: 8 in 3000 file a service against a coverid with no point. Unmappable, not unreal."""
    seed_service(buildable, 1, "missing")
    assert run(buildable, coverage_step())[COVERAGE_STEP] == 1
    row = buildable.execute("select geom from coverage").fetchone()
    assert row == (None,)


def test_repeated_filings_collapse_to_the_most_recent(
    buildable: psycopg.Connection[TupleRow],
) -> None:
    """(coverid, servprov, technolo) is filed more than once; the latest servstar wins."""
    seed_point(buildable, "c1", "56429,Αμυγδαλιάς,11,ΕΥΚΑΡΠΙΑ")
    seed_service(buildable, 1, "c1", maxdown=5, servstar="2024-01-01")
    seed_service(buildable, 2, "c1", maxdown=8, servstar="2026-01-01")
    assert run(buildable, coverage_step())[COVERAGE_STEP] == 1
    row = buildable.execute("select speed_band_id from coverage").fetchone()
    assert row == (8,)


def test_seller_and_builder_are_recorded_separately(
    buildable: psycopg.Connection[TupleRow],
) -> None:
    seed_point(buildable, "c1", "56429,Αμυγδαλιάς,11,ΕΥΚΑΡΠΙΑ")
    seed_service(buildable, 1, "c1", servprov=2, infrprov=13)
    run(buildable, coverage_step())
    row = buildable.execute(
        "select sp.code, ip.code from coverage c "
        "join provider sp on sp.id = c.provider_id "
        "join provider ip on ip.id = c.infra_provider_id"
    ).fetchone()
    assert row == ("VODAFONE", "FIBERGRID")


def test_family_always_agrees_with_technology(buildable: psycopg.Connection[TupleRow]) -> None:
    """Every register technology, routed to whichever table its geometry belongs in."""
    seed_point(buildable, "c1", "56429,Αμυγδαλιάς,11,ΕΥΚΑΡΠΙΑ")
    seed_cabinet(buildable, "c1")
    for n, technolo in enumerate([1, 2, 3, 4, 5, 13], start=1):
        seed_service(buildable, n, "c1", technolo=technolo)
    run(buildable, coverage_step() + area_step())
    rows = buildable.execute(
        "select c.technology, c.family, t.family from ("
        "  select technology, family from coverage union all"
        "  select technology, family from coverage_area"
        ") c join technology t on t.code = c.technology"
    ).fetchall()
    assert len(rows) == 6
    assert all(stored == expected for _, stored, expected in rows)


def test_copper_and_the_rest_are_routed_to_different_tables(
    buildable: psycopg.Connection[TupleRow],
) -> None:
    seed_point(buildable, "c1", "56429,Αμυγδαλιάς,11,ΕΥΚΑΡΠΙΑ")
    seed_cabinet(buildable, "c1")
    for n, technolo in enumerate([1, 2, 3, 4, 5, 13], start=1):
        seed_service(buildable, n, "c1", technolo=technolo)
    run(buildable, coverage_step() + area_step())
    points = buildable.execute("select technology from coverage order by technology").fetchall()
    areas = buildable.execute("select technology from coverage_area order by technology").fetchall()
    assert [r[0] for r in points] == ["DOCSIS", "FTTH", "OTHER"]
    assert [r[0] for r in areas] == ["ADSL", "VDSL", "VECT_VDSL"]


def test_rebuilding_refreshes_rather_than_duplicating(
    buildable: psycopg.Connection[TupleRow],
) -> None:
    seed_point(buildable, "c1", "56429,Αμυγδαλιάς,11,ΕΥΚΑΡΠΙΑ")
    seed_service(buildable, 1, "c1", maxdown=5)
    run(buildable, coverage_step())
    buildable.execute("update raw_wiredservice set maxdown = 8 where id = 1")
    buildable.commit()
    run(buildable, coverage_step())
    row = buildable.execute(
        "select count(*), max(speed_band_id), max(last_seen) >= max(first_seen) from coverage"
    ).fetchone()
    assert row == (1, 8, True)


def area_step() -> list[Step]:
    return [s for s in discover() if s.name == AREA_STEP]


# A cabinet service area in Greek Grid, around Kavala. Only the reprojection is under test.
CABINET = (
    '{"type": "MultiPolygon", "coordinates": '
    "[[[[500000.0, 4520000.0], [500500.0, 4520000.0], [500500.0, 4520500.0], [500000.0, 4520000.0]]]]}"
)


def seed_cabinet(conn: psycopg.Connection[TupleRow], coverid: str = "397-112") -> None:
    conn.execute(
        "insert into raw_geo_coverage_copper (coverid, geom) "
        "values (%s, st_setsrid(st_geomfromgeojson(%s), 2100))",
        (coverid, CABINET),
    )
    conn.commit()


def test_copper_becomes_an_area_not_a_point(buildable: psycopg.Connection[TupleRow]) -> None:
    """Copper service ids match the polygon tables and never the point table."""
    seed_cabinet(buildable)
    seed_service(buildable, 1, "397-112", technolo=3, maxdown=6)
    assert run(buildable, area_step())[AREA_STEP] == 1
    row = buildable.execute(
        "select technology, family, speed_band_id from coverage_area"
    ).fetchone()
    assert row == ("VECT_VDSL", "copper", 6)


def test_copper_is_kept_out_of_the_point_table(buildable: psycopg.Connection[TupleRow]) -> None:
    """Otherwise a cabinet arrives in coverage with no geometry and is silently unmappable."""
    seed_cabinet(buildable)
    seed_service(buildable, 1, "397-112", technolo=3)
    run(buildable, coverage_step())
    row = buildable.execute("select count(*) from coverage").fetchone()
    assert row == (0,)


def test_fibre_is_kept_out_of_the_area_table(buildable: psycopg.Connection[TupleRow]) -> None:
    seed_point(buildable, "c1", "56429,Αμυγδαλιάς,11,ΕΥΚΑΡΠΙΑ")
    seed_service(buildable, 1, "c1", technolo=4)
    assert run(buildable, area_step())[AREA_STEP] == 0


def test_the_cabinet_polygon_is_reprojected(buildable: psycopg.Connection[TupleRow]) -> None:
    """Greek Grid metres into WGS84 degrees: unreprojected, this lands in the Atlantic."""
    seed_cabinet(buildable)
    seed_service(buildable, 1, "397-112", technolo=3)
    run(buildable, area_step())
    row = buildable.execute(
        "select round(st_x(st_centroid(geom::geometry))::numeric, 1), "
        "round(st_y(st_centroid(geom::geometry))::numeric, 1) from coverage_area"
    ).fetchone()
    assert row is not None
    lon, lat = float(row[0]), float(row[1])
    assert 19.0 < lon < 30.0
    assert 34.0 < lat < 42.0


def test_the_area_stays_a_polygon(buildable: psycopg.Connection[TupleRow]) -> None:
    """A 400m cabinet flattened to its centroid loses every street it serves."""
    seed_cabinet(buildable)
    seed_service(buildable, 1, "397-112", technolo=3)
    run(buildable, area_step())
    row = buildable.execute(
        "select st_geometrytype(geom::geometry), st_area(geom) > 0 from coverage_area"
    ).fetchone()
    assert row == ("ST_MultiPolygon", True)


def test_a_cabinet_with_no_polygon_yields_nothing(
    buildable: psycopg.Connection[TupleRow],
) -> None:
    """Unlike a point service, an area with no geometry is not a usable row."""
    seed_service(buildable, 1, "no-such-cabinet", technolo=3)
    assert run(buildable, area_step())[AREA_STEP] == 0


def test_municipality_has_a_planar_twin(db: psycopg.Connection[TupleRow]) -> None:
    """Generated from geom, so the two can never disagree about where a municipality is."""
    row = db.execute(
        "select is_generated from information_schema.columns "
        "where table_name = 'municipality' and column_name = 'geom_2d'"
    ).fetchone()
    assert row == ("ALWAYS",)


def test_the_planar_twin_is_indexed(db: psycopg.Connection[TupleRow]) -> None:
    """Without the index the planar join is slower than the spheroid one it replaced."""
    rows = db.execute("select indexdef from pg_indexes where tablename = 'municipality'").fetchall()
    assert any("geom_2d" in definition and "gist" in definition for (definition,) in rows)


def test_planar_and_spheroid_agree_on_containment(
    buildable: psycopg.Connection[TupleRow],
) -> None:
    """The reason the swap is safe: identical answers on 200,000 real points, and here too."""
    seed_dimos(buildable)
    run(buildable, municipality_step())
    row = buildable.execute(
        "select st_contains(geom_2d, st_setsrid(st_point(24.05, 40.83), 4326)), "
        "st_intersects(geom, st_point(24.05, 40.83)::geography) from municipality"
    ).fetchone()
    assert row == (True, True)


def test_a_point_outside_agrees_too(buildable: psycopg.Connection[TupleRow]) -> None:
    seed_dimos(buildable)
    run(buildable, municipality_step())
    row = buildable.execute(
        "select st_contains(geom_2d, st_setsrid(st_point(25.0, 37.0), 4326)), "
        "st_intersects(geom, st_point(25.0, 37.0)::geography) from municipality"
    ).fetchone()
    assert row == (False, False)
