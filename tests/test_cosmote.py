from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
from psycopg.rows import TupleRow

from ingest.cosmote import Checked, checked, point_wkt, write

TZELILI = Checked(
    1, "ΘΕΣΣΑΛΟΝΙΚΗΣ", "ΛΑΓΚΑΔΑ", "ΛΑΓΚΑΔΑΣ", "ΟΔΟΣ", "ΑΧΙΛΛΕΑ ΤΖΕΛΙΛΗ", 40,
    "FBR_100M,FBR_50M,ADSL_24M", "2026-08-06 05:51:55",
    "POINT(23.0716 40.7471)", "rooftop", "19022ΕΚ00105",
)


@pytest.fixture
def scrape(db: psycopg.Connection[TupleRow]) -> Iterator[psycopg.Connection[TupleRow]]:
    db.execute("truncate raw_cosmote")
    db.commit()
    yield db
    db.execute("truncate raw_cosmote")
    db.commit()


def _sqlite(path: Path, rows: list[tuple[object, ...]]) -> Path:
    db = sqlite3.connect(path)
    db.execute(
        "create table coverage (id integer primary key, nomos text, dimos text, type text, "
        "name text, area text, number integer, plans text, timestamp text, lat real, lon real, "
        "geocode_precision text, geocode_type text, osm_id integer, osm_type text, "
        "display_name text, kaek text, parcel_area_sqm real, parcel_main_use text, "
        "parcel_extent text, parcel_polygon text)"
    )
    db.executemany(
        "insert into coverage (id, nomos, dimos, type, name, area, number, plans, timestamp, "
        "lat, lon, geocode_precision, kaek, parcel_polygon) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    db.commit()
    db.close()
    return path


def test_point_wkt() -> None:
    # 97 rows never got geocoded
    assert point_wkt(None, None) is None
    assert point_wkt(40.7471, None) is None
    assert point_wkt(40.7471, 23.0716) == "POINT(23.0716 40.7471)"


def test_write(scrape: psycopg.Connection[TupleRow]) -> None:
    assert write(scrape, iter([TZELILI])) == 1
    row = scrape.execute("select dimos, street, street_no, plans, kaek, st_srid(geom::geometry) from raw_cosmote").fetchone()
    assert row == ("ΛΑΓΚΑΔΑ", "ΑΧΙΛΛΕΑ ΤΖΕΛΙΛΗ", 40, "FBR_100M,FBR_50M,ADSL_24M", "19022ΕΚ00105", 4326)

    other = Checked(2, "ΑΤΤΙΚΗΣ", "ΑΘΗΝΑΙΩΝ", "ΑΘΗΝΑ", "ΟΔΟΣ", "ΑΧΑΡΝΩΝ", 1, "FBR_1G",
                    "2026-07-01 10:00:00", "POINT(23.73 37.99)", "rooftop", None)
    assert write(scrape, iter([other])) == 1
    assert scrape.execute("select id from raw_cosmote").fetchall() == [(2,)]


def test_checked(tmp_path: Path) -> None:
    path = _sqlite(tmp_path / "s.db", [(
        1, "ΘΕΣΣΑΛΟΝΙΚΗΣ", "ΛΑΓΚΑΔΑ", "ΟΔΟΣ", "ΑΧΙΛΛΕΑ ΤΖΕΛΙΛΗ", "ΛΑΓΚΑΔΑΣ", 40,
        "FBR_100M", "2026-08-06 05:51:55", 40.7471, 23.0716, "rooftop", "19022ΕΚ00105",
        "x" * 40000,
    )])
    rows = list(checked(path))
    assert len(rows) == 1
    assert rows[0].street == "ΑΧΙΛΛΕΑ ΤΖΕΛΙΛΗ"
    assert rows[0].wkt == "POINT(23.0716 40.7471)"
    assert "x" * 40000 not in str(rows[0])  # parcel polygons never read

    # no plans means asked and silent, not a no
    path = _sqlite(tmp_path / "s2.db", [
        (1, "Ν", "Δ", "ΟΔΟΣ", "Α", "Π", 1, "", "2026-08-06 05:51:55", 40.0, 23.0, "rooftop", None, None),
        (2, "Ν", "Δ", "ΟΔΟΣ", "Β", "Π", 2, None, "2026-08-06 05:51:55", 40.0, 23.0, "rooftop", None, None),
        (3, "Ν", "Δ", "ΟΔΟΣ", "Γ", "Π", 3, "FBR_1G", "2026-08-06 05:51:55", 40.0, 23.0, "rooftop", None, None),
    ])
    assert [r.id for r in checked(path)] == [3]
