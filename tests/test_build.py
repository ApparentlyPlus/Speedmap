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
OFFER_STEP = "050_address_coverage"

TOUCHED = (
    "municipality, raw_dimos, address, raw_coverpoint, coverage, coverage_area, "
    "raw_wiredservice, raw_geo_coverage_copper, address_coverage, raw_wireless_grid"
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
    """Unplaced is a real answer. The nearest municipality would be a guess."""
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
    """6.43% of points carry two. Both must be findable, and they share one geometry."""
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
    """(coverid, servprov, technolo) is filed more than once. The latest servstar wins."""
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


def links(conn: psycopg.Connection[TupleRow]) -> list[tuple[str, str]]:
    rows = conn.execute(
        "select a.street, ap.coverid from address_point ap "
        "join address a on a.id = ap.address_id order by a.street, ap.coverid"
    ).fetchall()
    return [(str(street), str(coverid)) for street, coverid in rows]


def test_an_address_is_linked_to_its_point(buildable: psycopg.Connection[TupleRow]) -> None:
    seed_point(buildable, "c1", "56429,Αμυγδαλιάς,11,ΕΥΚΑΡΠΙΑ")
    build_addresses(buildable)
    assert links(buildable) == [("Αμυγδαλιάς", "c1")]


def test_a_corner_point_links_to_both_of_its_addresses(
    buildable: psycopg.Connection[TupleRow],
) -> None:
    seed_point(buildable, "c1", "26332,ΠΑΡΟΔΟΣ ΑΝΑΓΝΩΣΤΟΥ,10,Δ. ΠΑΤΡΕΩΝ|26332,ΑΝΑΓΝΩΣΤΟΥ,10,Δ. ΠΑΤΡΕΩΝ")
    build_addresses(buildable)
    assert links(buildable) == [("ΑΝΑΓΝΩΣΤΟΥ", "c1"), ("ΠΑΡΟΔΟΣ ΑΝΑΓΝΩΣΤΟΥ", "c1")]


def test_two_builders_at_one_address_both_link(
    buildable: psycopg.Connection[TupleRow],
) -> None:
    """404,423 addresses are filed by two builders. Losing one loses an operator's footprint."""
    seed_point(buildable, "c1", "56429,Αμυγδαλιάς,11,ΕΥΚΑΡΠΙΑ")
    seed_point(buildable, "c2", "56429,Αμυγδαλιάς,11,ΕΥΚΑΡΠΙΑ")
    build_addresses(buildable)
    assert links(buildable) == [("Αμυγδαλιάς", "c1"), ("Αμυγδαλιάς", "c2")]
    row = buildable.execute("select count(*) from address").fetchone()
    assert row == (1,)


def test_a_point_with_no_street_is_linked_to_nothing(
    buildable: psycopg.Connection[TupleRow],
) -> None:
    """5.19% of the register's points have no street name, holding 3.50% of all premises.
    They keep their geometry and their coverage. They are simply not searchable."""
    seed_point(buildable, "c1", "24400, , ,Δ. ΓΑΡΓΑΛΙΑΝΩΝ")
    assert build_addresses(buildable) == 0
    assert links(buildable) == []


def test_rebuilding_does_not_duplicate_links(buildable: psycopg.Connection[TupleRow]) -> None:
    seed_point(buildable, "c1", "56429,Αμυγδαλιάς,11,ΕΥΚΑΡΠΙΑ")
    build_addresses(buildable)
    run(buildable, address_step())
    row = buildable.execute("select count(*) from address_point").fetchone()
    assert row == (1,)


def test_deleting_an_address_takes_its_links(buildable: psycopg.Connection[TupleRow]) -> None:
    seed_point(buildable, "c1", "56429,Αμυγδαλιάς,11,ΕΥΚΑΡΠΙΑ")
    build_addresses(buildable)
    buildable.execute("delete from address")
    row = buildable.execute("select count(*) from address_point").fetchone()
    assert row == (0,)


def offer_step() -> list[Step]:
    return [s for s in discover() if s.name == OFFER_STEP]


def offers(conn: psycopg.Connection[TupleRow]) -> list[tuple[str, str, str]]:
    rows = conn.execute(
        "select p.code, ac.technology, ac.matched_by from address_coverage ac "
        "join provider p on p.id = ac.provider_id order by p.code, ac.technology"
    ).fetchall()
    return [(str(a), str(b), str(c)) for a, b, c in rows]


# seed_cabinet is Greek Grid. This is its centroid once reprojected to 4326.
INSIDE = (24.0057, 40.8351)
OUTSIDE = (25.0, 37.0)


def build_offers(conn: psycopg.Connection[TupleRow]) -> int:
    run(conn, coverage_step() + area_step())
    return run(conn, offer_step())[OFFER_STEP]


def test_a_point_service_becomes_an_offer(buildable: psycopg.Connection[TupleRow]) -> None:
    seed_point(buildable, "c1", "56429,Αμυγδαλιάς,11,ΕΥΚΑΡΠΙΑ")
    build_addresses(buildable)
    seed_service(buildable, 1, "c1", technolo=4)
    assert build_offers(buildable) == 1
    assert offers(buildable) == [("METADOSIS", "FTTH", "point")]


def test_an_address_inside_a_cabinet_gets_its_copper(
    buildable: psycopg.Connection[TupleRow],
) -> None:
    """Copper is filed per cabinet, so every address in the area is served by it."""
    lon, lat = INSIDE
    seed_point(buildable, "c1", "56429,Αμυγδαλιάς,11,ΕΥΚΑΡΠΙΑ", lon=lon, lat=lat)
    build_addresses(buildable)
    seed_cabinet(buildable, "cab1")
    seed_service(buildable, 1, "cab1", technolo=3)
    assert build_offers(buildable) == 1
    assert offers(buildable) == [("METADOSIS", "VECT_VDSL", "area")]


def test_an_address_outside_the_cabinet_gets_nothing(
    buildable: psycopg.Connection[TupleRow],
) -> None:
    lon, lat = OUTSIDE
    seed_point(buildable, "c1", "56429,Αμυγδαλιάς,11,ΕΥΚΑΡΠΙΑ", lon=lon, lat=lat)
    build_addresses(buildable)
    seed_cabinet(buildable, "cab1")
    seed_service(buildable, 1, "cab1", technolo=3)
    assert build_offers(buildable) == 0


def test_a_point_match_beats_an_area_match(buildable: psycopg.Connection[TupleRow]) -> None:
    """A filing against this building is stronger evidence than falling inside a cabinet."""
    lon, lat = INSIDE
    seed_point(buildable, "c1", "56429,Αμυγδαλιάς,11,ΕΥΚΑΡΠΙΑ", lon=lon, lat=lat)
    build_addresses(buildable)
    seed_cabinet(buildable, "c1")
    seed_service(buildable, 1, "c1", technolo=3)
    seed_service(buildable, 2, "c1", technolo=4)
    build_offers(buildable)
    matched = buildable.execute(
        "select technology, matched_by from address_coverage order by technology"
    ).fetchall()
    assert [(str(t), str(m)) for t, m in matched] == [("FTTH", "point"), ("VECT_VDSL", "area")]


def test_several_operators_at_one_address(buildable: psycopg.Connection[TupleRow]) -> None:
    """59.57% of addresses have three operators. Collapsing them would hide competition."""
    seed_point(buildable, "c1", "56429,Αμυγδαλιάς,11,ΕΥΚΑΡΠΙΑ")
    build_addresses(buildable)
    seed_service(buildable, 1, "c1", servprov=19, technolo=4)
    seed_service(buildable, 2, "c1", servprov=2, technolo=4)
    seed_service(buildable, 3, "c1", servprov=15, technolo=4)
    assert build_offers(buildable) == 3
    assert offers(buildable) == [
        ("METADOSIS", "FTTH", "point"),
        ("NOVA", "FTTH", "point"),
        ("VODAFONE", "FTTH", "point"),
    ]


def test_an_offer_may_have_no_speed(buildable: psycopg.Connection[TupleRow]) -> None:
    """72.8% of fibre offers carry no band. Absent must survive the whole pipeline."""
    seed_point(buildable, "c1", "56429,Αμυγδαλιάς,11,ΕΥΚΑΡΠΙΑ")
    build_addresses(buildable)
    seed_service(buildable, 1, "c1", technolo=4, maxdown=None)
    build_offers(buildable)
    row = buildable.execute("select speed_band_id from address_coverage").fetchone()
    assert row == (None,)


def test_rebuilding_offers_is_idempotent(buildable: psycopg.Connection[TupleRow]) -> None:
    seed_point(buildable, "c1", "56429,Αμυγδαλιάς,11,ΕΥΚΑΡΠΙΑ")
    build_addresses(buildable)
    seed_service(buildable, 1, "c1", technolo=4)
    build_offers(buildable)
    run(buildable, offer_step())
    row = buildable.execute("select count(*) from address_coverage").fetchone()
    assert row == (1,)


def test_case_and_accent_variants_are_one_address(
    buildable: psycopg.Connection[TupleRow],
) -> None:
    """59,899 duplicates existed because street was keyed verbatim: ΑΧΑΡΝΩΝ vs Αχαρνών."""
    seed_point(buildable, "c1", "10446,ΑΧΑΡΝΩΝ,128,ΑΘΗΝΑ")
    seed_point(buildable, "c2", "10446,Αχαρνών,128,Δ. ΑΘΗΝΑΙΩΝ")
    assert build_addresses(buildable) == 1
    row = buildable.execute("select street_fold from address").fetchone()
    assert row == ("ΑΧΑΡΝΩΝ",)


def test_both_variants_still_link_to_their_points(
    buildable: psycopg.Connection[TupleRow],
) -> None:
    """Collapsing the address must not drop either builder's footprint."""
    seed_point(buildable, "c1", "10446,ΑΧΑΡΝΩΝ,128,ΑΘΗΝΑ")
    seed_point(buildable, "c2", "10446,Αχαρνών,128,Δ. ΑΘΗΝΑΙΩΝ")
    build_addresses(buildable)
    assert [c for _, c in links(buildable)] == ["c1", "c2"]


def test_a_type_word_does_not_make_a_second_address(
    buildable: psycopg.Connection[TupleRow],
) -> None:
    """ΛΕΩΦ. ΑΛΕΞΑΝΔΡΑΣ 5 and ΑΛΕΞΑΝΔΡΑΣ 5 are one place. The type word is not identity."""
    seed_point(buildable, "c1", "11473,ΛΕΩΦΟΡΟΣ ΑΛΕΞΑΝΔΡΑΣ,5,ΑΘΗΝΑ")
    seed_point(buildable, "c2", "11473,ΑΛΕΞΑΝΔΡΑΣ,5,ΑΘΗΝΑ")
    assert build_addresses(buildable) == 1
    row = buildable.execute("select street_fold from address").fetchone()
    assert row == ("ΑΛΕΞΑΝΔΡΑΣ",)


def test_the_displayed_spelling_is_deterministic(
    buildable: psycopg.Connection[TupleRow],
) -> None:
    """Which spelling survives must not depend on row order, or rebuilds churn the data."""
    seed_point(buildable, "c1", "10446,ΑΧΑΡΝΩΝ,128,ΑΘΗΝΑ")
    seed_point(buildable, "c2", "10446,Αχαρνών,128,ΑΘΗΝΑ")
    build_addresses(buildable)
    first = buildable.execute("select street from address").fetchone()
    run(buildable, address_step())
    assert buildable.execute("select street from address").fetchone() == first


def test_a_latin_key_is_written_for_addresses(
    buildable: psycopg.Connection[TupleRow],
) -> None:
    """Greeklish searches the Latin form of the same key, so both must come from one source."""
    seed_point(buildable, "c1", "56429,Αχαρνών,11,ΕΥΚΑΡΠΙΑ")
    build_addresses(buildable)
    row = buildable.execute("select search_key, latin_key from address").fetchone()
    assert row == ("ΑΧΑΡΝΩΝ ΕΥΚΑΡΠΙΑ", "AXARNON EFKARPIA")


def test_the_latin_key_covers_the_locality_too(
    buildable: psycopg.Connection[TupleRow],
) -> None:
    """Typing the town in Greeklish must narrow the same way typing it in Greek does."""
    seed_point(buildable, "c1", "15123,ΛΕΩΦΟΡΟΣ ΙΩΑΝΝΗ ΚΑΠΟΔΙΣΤΡΙΟΥ,18,Δ. ΑΜΑΡΟΥΣΙΟΥ")
    build_addresses(buildable)
    row = buildable.execute("select latin_key from address").fetchone()
    assert row == ("IOANNI KAPODISTRIU AMARUSIU",)


WIRELESS_STEP = "070_wireless"

# The cell the default seed_point lands in. Pinned as a literal, so changing the projection
# the grid is read in fails here rather than silently moving every address.
CELL = "5040|45196"


def wireless_step() -> list[Step]:
    return [s for s in discover() if s.name == WIRELESS_STEP]


def seed_cell(
    conn: psycopg.Connection[TupleRow],
    gridid: str = CELL,
    *,
    row_id: int = 1,
    servprov: int = 1,
    tech4gm: int = 0,
    tech5gm: int = 0,
    tech4gf: int = 0,
    tech5gf: int = 0,
    maxdown: int = 7,
) -> None:
    conn.execute(
        "insert into raw_wireless_grid "
        "(id, gridid, servprov, tech4gm, tech5gm, tech4gf, tech5gf, maxdown) "
        "values (%s, %s, %s, %s, %s, %s, %s, %s)",
        (row_id, gridid, servprov, tech4gm, tech5gm, tech4gf, tech5gf, maxdown),
    )
    conn.commit()


def cells(conn: psycopg.Connection[TupleRow]) -> list[tuple[str, str, int | None]]:
    rows = conn.execute(
        "select technology, matched_by, speed_band_id from address_coverage "
        "where matched_by = 'cell' order by technology"
    ).fetchall()
    return [(str(t), str(m), b) for t, m, b in rows]


def build_cells(conn: psycopg.Connection[TupleRow]) -> int:
    return run(conn, wireless_step())[WIRELESS_STEP]


def test_a_fixed_wireless_cell_becomes_an_offer(buildable: psycopg.Connection[TupleRow]) -> None:
    """An address finds its cell by arithmetic, so the grid needs no geometry of its own."""
    seed_point(buildable, "c1", "56429,Αμυγδαλιάς,11,ΕΥΚΑΡΠΙΑ")
    build_addresses(buildable)
    seed_cell(buildable, tech5gf=1)
    assert build_cells(buildable) == 1
    assert cells(buildable) == [("FWA_5G", "cell", 7)]


def test_an_address_in_another_cell_gets_nothing(buildable: psycopg.Connection[TupleRow]) -> None:
    seed_point(buildable, "c1", "56429,Αμυγδαλιάς,11,ΕΥΚΑΡΠΙΑ")
    build_addresses(buildable)
    seed_cell(buildable, "5041|45196", tech5gf=1)
    assert build_cells(buildable) == 0


def test_a_mobile_cell_is_not_a_landline(buildable: psycopg.Connection[TupleRow]) -> None:
    """Mobile coverage cannot replace a fixed line, and 40.5M of the 53.3M rows are only that."""
    seed_point(buildable, "c1", "56429,Αμυγδαλιάς,11,ΕΥΚΑΡΠΙΑ")
    build_addresses(buildable)
    seed_cell(buildable, tech4gm=1, tech5gm=1)
    assert build_cells(buildable) == 0


def test_a_planned_cell_is_not_yet_an_offer(buildable: psycopg.Connection[TupleRow]) -> None:
    """A flag of 2 means planned within two years. Truthiness would sell it as available."""
    seed_point(buildable, "c1", "56429,Αμυγδαλιάς,11,ΕΥΚΑΡΠΙΑ")
    build_addresses(buildable)
    seed_cell(buildable, tech5gf=2)
    assert build_cells(buildable) == 0


def test_the_offer_is_named_for_the_best_generation(
    buildable: psycopg.Connection[TupleRow],
) -> None:
    """One band is filed per cell, so splitting the row would credit 4G with the 5G figure."""
    seed_point(buildable, "c1", "56429,Αμυγδαλιάς,11,ΕΥΚΑΡΠΙΑ")
    build_addresses(buildable)
    seed_cell(buildable, tech4gf=1, tech5gf=1)
    assert build_cells(buildable) == 1
    assert cells(buildable) == [("FWA_5G", "cell", 7)]


def test_a_cell_without_5g_stays_4g(buildable: psycopg.Connection[TupleRow]) -> None:
    seed_point(buildable, "c1", "56429,Αμυγδαλιάς,11,ΕΥΚΑΡΠΙΑ")
    build_addresses(buildable)
    seed_cell(buildable, tech4gf=1, maxdown=4)
    assert build_cells(buildable) == 1
    assert cells(buildable) == [("FWA_4G", "cell", 4)]


def test_an_uncovered_band_is_not_a_speed(buildable: psycopg.Connection[TupleRow]) -> None:
    """The wireless band list adds a zero for not covered, which speed_band has no row for."""
    seed_point(buildable, "c1", "56429,Αμυγδαλιάς,11,ΕΥΚΑΡΠΙΑ")
    build_addresses(buildable)
    seed_cell(buildable, tech5gf=1, maxdown=0)
    assert build_cells(buildable) == 1
    assert cells(buildable) == [("FWA_5G", "cell", None)]


def test_the_wireless_step_is_re_runnable(buildable: psycopg.Connection[TupleRow]) -> None:
    seed_point(buildable, "c1", "56429,Αμυγδαλιάς,11,ΕΥΚΑΡΠΙΑ")
    build_addresses(buildable)
    seed_cell(buildable, tech5gf=1)
    build_cells(buildable)
    build_cells(buildable)
    assert cells(buildable) == [("FWA_5G", "cell", 7)]
