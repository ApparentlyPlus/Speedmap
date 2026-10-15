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
WIRELESS_STEP = "070_wireless"

TOUCHED = (
    "municipality, raw_dimos, address, raw_coverpoint, coverage, coverage_area, "
    "raw_wiredservice, raw_geo_coverage_copper, address_coverage, raw_wireless_grid"
)

# ΔΗΜΟΣ ΠΑΓΓΑΙΟΥ as a triangle
POLYGON = '{"type": "MultiPolygon", "coordinates": [[[[24.0, 40.8], [24.1, 40.8], [24.1, 40.9], [24.0, 40.8]]]]}'

# a copper cabinet in Greek Grid near Kavala
CABINET = (
    '{"type": "MultiPolygon", "coordinates": '
    "[[[[500000.0, 4520000.0], [500500.0, 4520000.0], [500500.0, 4520500.0], [500000.0, 4520000.0]]]]}"
)
INSIDE = (24.0057, 40.8351)  # the cabinet's centroid in 4326
OUTSIDE = (25.0, 37.0)

# where seed_point's default lands on the wireless grid, written out so a projection change shows up
CELL = "5040|45196"

AMYG = "56429,Αμυγδαλιάς,11,ΕΥΚΑΡΠΙΑ"
CORNER = "26332,ΠΑΡΟΔΟΣ ΑΝΑΓΝΩΣΤΟΥ,10,Δ. ΠΑΤΡΕΩΝ|26332,ΑΝΑΓΝΩΣΤΟΥ,10,Δ. ΠΑΤΡΕΩΝ"


def _reset(conn: psycopg.Connection[TupleRow]) -> None:
    conn.execute(f"truncate {TOUCHED} cascade")
    conn.commit()


@pytest.fixture
def buildable(db: psycopg.Connection[TupleRow]) -> Iterator[psycopg.Connection[TupleRow]]:
    _reset(db)
    yield db
    _reset(db)


def _step(name: str) -> list[Step]:
    return [s for s in discover() if s.name == name]


def municipality_step() -> list[Step]:
    return _step("010_municipality")


def seed_dimos(conn: psycopg.Connection[TupleRow], gid: int = 1, name: str = "ΔΗΜΟΣ ΠΑΓΓΑΙΟΥ") -> None:
    conn.execute(
        "insert into raw_dimos (gid, kalcode4, d1, geom4326) values (%s, '0503', %s, st_setsrid(st_geomfromgeojson(%s), 4326))",
        (gid, name, POLYGON),
    )
    conn.commit()


def seed_point(conn: psycopg.Connection[TupleRow], coverid: str, address: str, *, lon: float = 24.05,
               lat: float = 40.83, prempass: int | None = 4, connstat: int | None = 1, vhcn: int | None = 1) -> None:
    conn.execute(
        "insert into raw_coverpoint (coverid, address, prempass, connstat, vhcn, point) "
        "values (%s, %s, %s, %s, %s, st_setsrid(st_point(%s, %s), 4326))",
        (coverid, address, prempass, connstat, vhcn, lon, lat),
    )
    conn.commit()


def build_addresses(conn: psycopg.Connection[TupleRow]) -> int:
    seed_dimos(conn)
    run(conn, municipality_step())
    return run(conn, _step(ADDRESS_STEP))[ADDRESS_STEP]


def _service(conn: psycopg.Connection[TupleRow], id_: int, coverid: str, *, servprov: int = 19, infrprov: int = 1,
             technolo: int = 4, maxdown: int | None = None, servstar: str | None = "2026-01-01") -> None:
    conn.execute(
        "insert into raw_wiredservice (id, coverid, servprov, infrprov, technolo, maxdown, servstar) "
        "values (%s, %s, %s, %s, %s, %s, %s)",
        (id_, coverid, servprov, infrprov, technolo, maxdown, servstar),
    )
    conn.commit()


def _cabinet(conn: psycopg.Connection[TupleRow], coverid: str = "397-112") -> None:
    conn.execute(
        "insert into raw_geo_coverage_copper (coverid, geom) values (%s, st_setsrid(st_geomfromgeojson(%s), 2100))",
        (coverid, CABINET),
    )
    conn.commit()


def _cell(conn: psycopg.Connection[TupleRow], gridid: str = CELL, *, tech4gm: int = 0, tech5gm: int = 0,
          tech4gf: int = 0, tech5gf: int = 0, maxdown: int = 7) -> None:
    conn.execute(
        "insert into raw_wireless_grid (id, gridid, servprov, tech4gm, tech5gm, tech4gf, tech5gf, maxdown) "
        "values (1, %s, 1, %s, %s, %s, %s, %s)",
        (gridid, tech4gm, tech5gm, tech4gf, tech5gf, maxdown),
    )
    conn.commit()


def _one(conn: psycopg.Connection[TupleRow], sql: str) -> TupleRow | None:
    return conn.execute(sql).fetchone()


def _links(conn: psycopg.Connection[TupleRow]) -> list[tuple[str, str]]:
    rows = conn.execute(
        "select a.street, ap.coverid from address_point ap join address a on a.id = ap.address_id "
        "order by a.street, ap.coverid"
    ).fetchall()
    return [(str(street), str(coverid)) for street, coverid in rows]


def _offers(conn: psycopg.Connection[TupleRow]) -> list[tuple[str, str, str]]:
    rows = conn.execute(
        "select p.code, ac.technology, ac.matched_by from address_coverage ac "
        "join provider p on p.id = ac.provider_id order by p.code, ac.technology"
    ).fetchall()
    return [(str(a), str(b), str(c)) for a, b, c in rows]


def _cells(conn: psycopg.Connection[TupleRow]) -> list[tuple[str, str, int | None]]:
    rows = conn.execute(
        "select technology, matched_by, speed_band_id from address_coverage where matched_by = 'cell' order by technology"
    ).fetchall()
    return [(str(t), str(m), b) for t, m, b in rows]


def _build_offers(conn: psycopg.Connection[TupleRow]) -> int:
    run(conn, _step(COVERAGE_STEP) + _step(AREA_STEP))
    return run(conn, _step(OFFER_STEP))[OFFER_STEP]


def _build_cells(conn: psycopg.Connection[TupleRow]) -> int:
    return run(conn, _step(WIRELESS_STEP))[WIRELESS_STEP]


def _fresh(conn: psycopg.Connection[TupleRow], *points: tuple[str, str], lon: float = 24.05, lat: float = 40.83,
           prempass: int | None = 4, connstat: int | None = 1, vhcn: int | None = 1) -> int:
    _reset(conn)
    for coverid, address in points:
        seed_point(conn, coverid, address, lon=lon, lat=lat, prempass=prempass, connstat=connstat, vhcn=vhcn)
    return build_addresses(conn)


def test_discover() -> None:
    names = [s.name for s in discover()]
    assert names == sorted(names)


def test_municipality(buildable: psycopg.Connection[TupleRow]) -> None:
    seed_dimos(buildable)
    run(buildable, municipality_step())
    assert _one(buildable, "select id, kallikratis_code, name from municipality") == (1, "0503", "ΔΗΜΟΣ ΠΑΓΓΑΙΟΥ")
    run(buildable, municipality_step())
    assert _one(buildable, "select count(*) from municipality") == (1,)

    # spherical joins later on, so geography
    row = _one(buildable, "select udt_name from information_schema.columns where table_name = 'municipality' and column_name = 'geom'")
    assert row == ("geography",)
    row = _one(buildable, "select name from municipality where st_intersects(geom, st_point(24.05, 40.83)::geography)")
    assert row == ("ΔΗΜΟΣ ΠΑΓΓΑΙΟΥ",)
    # outside is unplaced, nearest would be a guess
    row = _one(buildable, "select count(*) from municipality where st_intersects(geom, st_point(25.0, 37.0)::geography)")
    assert row == (0,)

    # geom_2d agrees with the spheroid, checked on 200,000 real points too
    row = _one(buildable, "select st_contains(geom_2d, st_setsrid(st_point(24.05, 40.83), 4326)), "
                          "st_intersects(geom, st_point(24.05, 40.83)::geography) from municipality")
    assert row == (True, True)
    row = _one(buildable, "select st_contains(geom_2d, st_setsrid(st_point(25.0, 37.0), 4326)), "
                          "st_intersects(geom, st_point(25.0, 37.0)::geography) from municipality")
    assert row == (False, False)

    buildable.execute("update raw_dimos set d1 = 'ΔΗΜΟΣ ΑΛΛΟΣ' where gid = 1")
    buildable.commit()
    run(buildable, municipality_step())
    assert _one(buildable, "select name from municipality") == ("ΔΗΜΟΣ ΑΛΛΟΣ",)


def test_municipality_2d(db: psycopg.Connection[TupleRow]) -> None:
    row = db.execute(
        "select is_generated from information_schema.columns where table_name = 'municipality' and column_name = 'geom_2d'"
    ).fetchone()
    assert row == ("ALWAYS",)
    # unindexed it's slower than the spheroid join it replaced
    rows = db.execute("select indexdef from pg_indexes where tablename = 'municipality'").fetchall()
    assert any("geom_2d" in d and "gist" in d for (d,) in rows)


def test_addresses(buildable: psycopg.Connection[TupleRow]) -> None:
    assert _fresh(buildable, ("a", AMYG)) == 1
    assert _one(buildable, "select postcode, street, street_no, locality, premises from address") == ("56429", "Αμυγδαλιάς", "11", "ΕΥΚΑΡΠΙΑ", 4)
    # locality as filed, municipality from the point
    row = _one(buildable, "select a.locality, m.name from address a join municipality m on m.id = a.municipality_id")
    assert row == ("ΕΥΚΑΡΠΙΑ", "ΔΗΜΟΣ ΠΑΓΓΑΙΟΥ")

    buildable.execute("update raw_coverpoint set prempass = 12 where coverid = 'a'")
    buildable.commit()
    run(buildable, _step(ADDRESS_STEP))
    assert _one(buildable, "select count(*), max(premises) from address") == (1, 12)

    assert _fresh(buildable, ("a", CORNER)) == 2
    rows = buildable.execute("select street from address order by street").fetchall()
    assert [r[0] for r in rows] == ["ΑΝΑΓΝΩΣΤΟΥ", "ΠΑΡΟΔΟΣ ΑΝΑΓΝΩΣΤΟΥ"]

    _reset(buildable)
    seed_point(buildable, "a", AMYG, prempass=4)
    seed_point(buildable, "b", AMYG, prempass=9)
    assert build_addresses(buildable) == 1
    assert _one(buildable, "select premises from address") == (9,)

    # outside every municipality, still searchable
    assert _fresh(buildable, ("a", AMYG), lon=25.0, lat=37.0) == 1
    assert _one(buildable, "select municipality_id from address") == (None,)

    assert _fresh(buildable, ("a", "56431,,1,ΣΤΑΥΡΟΥΠΟΛΗ")) == 0


def test_address_flags(buildable: psycopg.Connection[TupleRow]) -> None:
    # missing connstat is unknown, not "not connected"
    _fresh(buildable, ("a", AMYG), prempass=None, connstat=None, vhcn=None)
    assert _one(buildable, "select premises, connected, vhcn from address") == (None, None, None)

    _fresh(buildable, ("a", AMYG), connstat=0)
    assert _one(buildable, "select connected from address") == (False,)


def test_address_keys(buildable: psycopg.Connection[TupleRow]) -> None:
    _fresh(buildable, ("a", "15123,ΛΕΩΦΟΡΟΣ ΙΩΑΝΝΗ ΚΑΠΟΔΙΣΤΡΙΟΥ,18,Δ. ΑΜΑΡΟΥΣΙΟΥ"))
    assert _one(buildable, "select search_key from address") == ("ΙΩΑΝΝΗ ΚΑΠΟΔΙΣΤΡΙΟΥ ΑΜΑΡΟΥΣΙΟΥ",)
    assert _one(buildable, "select latin_key from address") == ("IOANNI KAPODISTRIU AMARUSIU",)

    _fresh(buildable, ("c1", "56429,Αχαρνών,11,ΕΥΚΑΡΠΙΑ"))
    assert _one(buildable, "select search_key, latin_key from address") == ("ΑΧΑΡΝΩΝ ΕΥΚΑΡΠΙΑ", "AXARNON EFKARPIA")

    # 59,899 duplicates when street was keyed verbatim
    assert _fresh(buildable, ("c1", "10446,ΑΧΑΡΝΩΝ,128,ΑΘΗΝΑ"), ("c2", "10446,Αχαρνών,128,Δ. ΑΘΗΝΑΙΩΝ")) == 1
    assert _one(buildable, "select street_fold from address") == ("ΑΧΑΡΝΩΝ",)
    assert [c for _, c in _links(buildable)] == ["c1", "c2"]

    assert _fresh(buildable, ("c1", "11473,ΛΕΩΦΟΡΟΣ ΑΛΕΞΑΝΔΡΑΣ,5,ΑΘΗΝΑ"), ("c2", "11473,ΑΛΕΞΑΝΔΡΑΣ,5,ΑΘΗΝΑ")) == 1
    assert _one(buildable, "select street_fold from address") == ("ΑΛΕΞΑΝΔΡΑΣ",)

    # whichever spelling wins has to win every rebuild
    _fresh(buildable, ("c1", "10446,ΑΧΑΡΝΩΝ,128,ΑΘΗΝΑ"), ("c2", "10446,Αχαρνών,128,ΑΘΗΝΑ"))
    first = _one(buildable, "select street from address")
    run(buildable, _step(ADDRESS_STEP))
    assert _one(buildable, "select street from address") == first


def test_links(buildable: psycopg.Connection[TupleRow]) -> None:
    _fresh(buildable, ("c1", AMYG))
    assert _links(buildable) == [("Αμυγδαλιάς", "c1")]
    run(buildable, _step(ADDRESS_STEP))
    assert _one(buildable, "select count(*) from address_point") == (1,)
    buildable.execute("delete from address")
    assert _one(buildable, "select count(*) from address_point") == (0,)

    _fresh(buildable, ("c1", CORNER))
    assert _links(buildable) == [("ΑΝΑΓΝΩΣΤΟΥ", "c1"), ("ΠΑΡΟΔΟΣ ΑΝΑΓΝΩΣΤΟΥ", "c1")]

    # 404,423 addresses have two builders
    _fresh(buildable, ("c1", AMYG), ("c2", AMYG))
    assert _links(buildable) == [("Αμυγδαλιάς", "c1"), ("Αμυγδαλιάς", "c2")]
    assert _one(buildable, "select count(*) from address") == (1,)

    # 5.19% of points have no street
    assert _fresh(buildable, ("c1", "24400, , ,Δ. ΓΑΡΓΑΛΙΑΝΩΝ")) == 0
    assert _links(buildable) == []


def test_coverage(buildable: psycopg.Connection[TupleRow]) -> None:
    seed_point(buildable, "c1", AMYG)
    _service(buildable, 1, "c1", maxdown=8)
    assert run(buildable, _step(COVERAGE_STEP))[COVERAGE_STEP] == 1
    row = _one(
        buildable,
        "select c.source, sp.code, ip.code, c.technology, c.family, sb.label, c.assertion::text "
        "from coverage c join provider sp on sp.id = c.provider_id "
        "join provider ip on ip.id = c.infra_provider_id "
        "join speed_band sb on sb.id = c.speed_band_id",
    )
    assert row == ("register", "METADOSIS", "TELEKOM", "FTTH", "fiber", ">= 1000 Mbps", "declared")
    row = _one(buildable, "select round(st_x(geom::geometry)::numeric, 2) from coverage")
    assert row is not None
    assert float(row[0]) == 24.05

    buildable.execute("update raw_wiredservice set maxdown = 8 where id = 1")
    buildable.commit()
    run(buildable, _step(COVERAGE_STEP))
    assert _one(buildable, "select count(*), max(speed_band_id), max(last_seen) >= max(first_seen) from coverage") == (1, 8, True)

    # 73.3% of services file no band
    _reset(buildable)
    seed_point(buildable, "c1", AMYG)
    _service(buildable, 1, "c1", maxdown=None)
    run(buildable, _step(COVERAGE_STEP))
    assert _one(buildable, "select speed_band_id from coverage") == (None,)

    # 8 in 3000 point at a coverid that doesn't exist
    _reset(buildable)
    _service(buildable, 1, "missing")
    assert run(buildable, _step(COVERAGE_STEP))[COVERAGE_STEP] == 1
    assert _one(buildable, "select geom from coverage") == (None,)

    # filed more than once, latest servstar wins
    _reset(buildable)
    seed_point(buildable, "c1", AMYG)
    _service(buildable, 1, "c1", maxdown=5, servstar="2024-01-01")
    _service(buildable, 2, "c1", maxdown=8, servstar="2026-01-01")
    assert run(buildable, _step(COVERAGE_STEP))[COVERAGE_STEP] == 1
    assert _one(buildable, "select speed_band_id from coverage") == (8,)

    _reset(buildable)
    seed_point(buildable, "c1", AMYG)
    _service(buildable, 1, "c1", servprov=2, infrprov=13)
    run(buildable, _step(COVERAGE_STEP))
    row = _one(buildable, "select sp.code, ip.code from coverage c join provider sp on sp.id = c.provider_id "
                          "join provider ip on ip.id = c.infra_provider_id")
    assert row == ("VODAFONE", "FIBERGRID")


def test_coverage_routing(buildable: psycopg.Connection[TupleRow]) -> None:
    seed_point(buildable, "c1", AMYG)
    _cabinet(buildable, "c1")
    for n, technolo in enumerate([1, 2, 3, 4, 5, 13], start=1):
        _service(buildable, n, "c1", technolo=technolo)
    run(buildable, _step(COVERAGE_STEP) + _step(AREA_STEP))
    rows = buildable.execute(
        "select c.technology, c.family, t.family from ("
        "  select technology, family from coverage union all"
        "  select technology, family from coverage_area"
        ") c join technology t on t.code = c.technology"
    ).fetchall()
    assert len(rows) == 6
    assert all(stored == expected for _, stored, expected in rows)

    points = buildable.execute("select technology from coverage order by technology").fetchall()
    areas = buildable.execute("select technology from coverage_area order by technology").fetchall()
    assert [r[0] for r in points] == ["DOCSIS", "FTTH", "OTHER"]
    assert [r[0] for r in areas] == ["ADSL", "VDSL", "VECT_VDSL"]


def test_areas(buildable: psycopg.Connection[TupleRow]) -> None:
    _cabinet(buildable)
    _service(buildable, 1, "397-112", technolo=3, maxdown=6)
    assert run(buildable, _step(AREA_STEP))[AREA_STEP] == 1
    assert _one(buildable, "select technology, family, speed_band_id from coverage_area") == ("VECT_VDSL", "copper", 6)

    # reprojected, or it lands in the Atlantic
    row = _one(buildable, "select round(st_x(st_centroid(geom::geometry))::numeric, 1), "
                          "round(st_y(st_centroid(geom::geometry))::numeric, 1) from coverage_area")
    assert row is not None
    lon, lat = float(row[0]), float(row[1])
    assert 19.0 < lon < 30.0
    assert 34.0 < lat < 42.0
    # a centroid would lose every street the cabinet serves
    assert _one(buildable, "select st_geometrytype(geom::geometry), st_area(geom) > 0 from coverage_area") == ("ST_MultiPolygon", True)

    # and never in the point table, where it'd have no geometry
    run(buildable, _step(COVERAGE_STEP))
    assert _one(buildable, "select count(*) from coverage") == (0,)

    _reset(buildable)
    seed_point(buildable, "c1", AMYG)
    _service(buildable, 1, "c1", technolo=4)
    assert run(buildable, _step(AREA_STEP))[AREA_STEP] == 0

    _reset(buildable)
    _service(buildable, 1, "no-such-cabinet", technolo=3)
    assert run(buildable, _step(AREA_STEP))[AREA_STEP] == 0


def test_offers(buildable: psycopg.Connection[TupleRow]) -> None:
    _fresh(buildable, ("c1", AMYG))
    _service(buildable, 1, "c1", technolo=4)
    assert _build_offers(buildable) == 1
    assert _offers(buildable) == [("METADOSIS", "FTTH", "point")]
    run(buildable, _step(OFFER_STEP))
    assert _one(buildable, "select count(*) from address_coverage") == (1,)

    # 59.57% of addresses have three operators
    _fresh(buildable, ("c1", AMYG))
    _service(buildable, 1, "c1", servprov=19, technolo=4)
    _service(buildable, 2, "c1", servprov=2, technolo=4)
    _service(buildable, 3, "c1", servprov=15, technolo=4)
    assert _build_offers(buildable) == 3
    assert _offers(buildable) == [("METADOSIS", "FTTH", "point"), ("NOVA", "FTTH", "point"), ("VODAFONE", "FTTH", "point")]

    _fresh(buildable, ("c1", AMYG))
    _service(buildable, 1, "c1", technolo=4, maxdown=None)
    _build_offers(buildable)
    assert _one(buildable, "select speed_band_id from address_coverage") == (None,)


def test_offers_cabinet(buildable: psycopg.Connection[TupleRow]) -> None:
    lon, lat = INSIDE
    _fresh(buildable, ("c1", AMYG), lon=lon, lat=lat)
    _cabinet(buildable, "cab1")
    _service(buildable, 1, "cab1", technolo=3)
    assert _build_offers(buildable) == 1
    assert _offers(buildable) == [("METADOSIS", "VECT_VDSL", "area")]

    lon, lat = OUTSIDE
    _fresh(buildable, ("c1", AMYG), lon=lon, lat=lat)
    _cabinet(buildable, "cab1")
    _service(buildable, 1, "cab1", technolo=3)
    assert _build_offers(buildable) == 0

    lon, lat = INSIDE
    _fresh(buildable, ("c1", AMYG), lon=lon, lat=lat)
    _cabinet(buildable, "c1")
    _service(buildable, 1, "c1", technolo=3)
    _service(buildable, 2, "c1", technolo=4)
    _build_offers(buildable)
    matched = buildable.execute("select technology, matched_by from address_coverage order by technology").fetchall()
    assert [(str(t), str(m)) for t, m in matched] == [("FTTH", "point"), ("VECT_VDSL", "area")]

    # same line both ways keeps the door. The tie used to hang on 'area' sorting first
    _fresh(buildable, ("c1", AMYG), lon=lon, lat=lat)
    _cabinet(buildable, "cab1")
    _service(buildable, 1, "c1", technolo=4)
    _service(buildable, 2, "cab1", technolo=3)
    run(buildable, _step(COVERAGE_STEP) + _step(AREA_STEP))
    buildable.execute(
        "insert into coverage_area (source, source_ref, provider_id, technology, family, assertion, geom) "
        "select source, 'planted', provider_id, 'FTTH', 'fiber', assertion, geom from coverage_area"
    )
    buildable.commit()
    run(buildable, _step(OFFER_STEP))
    assert _offers(buildable) == [("METADOSIS", "FTTH", "point"), ("METADOSIS", "VECT_VDSL", "area")]


def test_wireless(buildable: psycopg.Connection[TupleRow]) -> None:
    _fresh(buildable, ("c1", AMYG))
    _cell(buildable, tech5gf=1)
    assert _build_cells(buildable) == 1
    assert _cells(buildable) == [("FWA_5G", "cell", 7)]
    _build_cells(buildable)
    assert _cells(buildable) == [("FWA_5G", "cell", 7)]

    _fresh(buildable, ("c1", AMYG))
    _cell(buildable, "5041|45196", tech5gf=1)
    assert _build_cells(buildable) == 0

    # 40.5M of the 53.3M rows are mobile only
    _fresh(buildable, ("c1", AMYG))
    _cell(buildable, tech4gm=1, tech5gm=1)
    assert _build_cells(buildable) == 0

    # 2 means planned
    _fresh(buildable, ("c1", AMYG))
    _cell(buildable, tech5gf=2)
    assert _build_cells(buildable) == 0


def test_wireless_bands(buildable: psycopg.Connection[TupleRow]) -> None:
    # the cell's one band is 5G's, 4G still qualifies
    _fresh(buildable, ("c1", AMYG))
    _cell(buildable, tech4gf=1, tech5gf=1)
    assert _build_cells(buildable) == 2
    assert sorted(_cells(buildable)) == [("FWA_4G", "cell", None), ("FWA_5G", "cell", 7)]

    _fresh(buildable, ("c1", AMYG))
    _cell(buildable, tech4gf=1, maxdown=4)
    assert _build_cells(buildable) == 1
    assert _cells(buildable) == [("FWA_4G", "cell", 4)]

    # 0 is "not covered", speed_band has no row 0
    _fresh(buildable, ("c1", AMYG))
    _cell(buildable, tech5gf=1, maxdown=0)
    assert _build_cells(buildable) == 1
    assert _cells(buildable) == [("FWA_5G", "cell", None)]
