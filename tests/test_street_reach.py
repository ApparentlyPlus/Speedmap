"""Who reaches a street, and how fast: one derivation, read two ways.

These used to be two steps.
"""

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

# A cabinet in Greek Grid, about 500 m on a side, and a street lying inside it.
CABINET_2100 = (
    '{"type": "MultiPolygon", "coordinates": '
    "[[[[500000.0, 4520000.0], [500500.0, 4520000.0], "
    "[500500.0, 4520500.0], [500000.0, 4520000.0]]]]}"
)

# Inside that cabinet once reprojected, as a line rather than a point: a street is a line.
INSIDE_LINE = "MULTILINESTRING((24.0050 40.8340, 24.0060 40.8350))"
OUTSIDE_LINE = "MULTILINESTRING((25.0000 37.0000, 25.0010 37.0010))"


@pytest.fixture
def reachable(db: psycopg.Connection[TupleRow]) -> Iterator[psycopg.Connection[TupleRow]]:
    db.execute(f"truncate {TOUCHED} cascade")
    db.execute(
        "insert into provider (code, display_name, kind) values ('TEST', 'Test', 'altnet') "
        "on conflict (code) do nothing"
    )
    db.execute(
        "insert into source (name, url) values ('register', 'https://example.invalid') "
        "on conflict (name) do nothing"
    )
    # A municipality both the street and its doors belong to.
    db.execute(
        "insert into municipality (id, kallikratis_code, name, geom) values "
        "(1, '0000', 'ΔΗΜΟΣ ΤΕΣΤ', %s) on conflict (id) do nothing",
        ("SRID=4326;MULTIPOLYGON(((24.0 40.8, 24.1 40.8, 24.1 40.9, 24.0 40.8)))",),
    )
    db.commit()
    yield db
    db.execute(f"truncate {TOUCHED} cascade")
    db.commit()


def steps() -> list[Step]:
    """The pin as well as the reach.

    110 reads `address.street_id` rather than matching on the name, so running it without
    065 would test a street with nothing attached to it and pass by finding nothing.
    Discovery returns them in filename order, which is the order they have to run in.
    """
    wanted = {PIN_STEP, REACH_STEP, SPEED_STEP}
    return [s for s in discover() if s.name in wanted]


def provider_id(conn: psycopg.Connection[TupleRow]) -> int:
    row = conn.execute("select id from provider where code = 'TEST'").fetchone()
    assert row is not None
    return int(row[0])


def seed_street(conn: psycopg.Connection[TupleRow], geom: str = INSIDE_LINE) -> int:
    row = conn.execute(
        "insert into street (name, name_fold, latin_key, sort_key, highway, ways, geom, "
        "municipality_id) values ('ΤΕΣΤ', 'ΤΕΣΤ', 'TEST', 'ΤΕΣΤ', 'residential', 1, %s, 1) "
        "returning id",
        (f"SRID=4326;{geom}",),
    ).fetchone()
    conn.commit()
    assert row is not None
    return int(row[0])


def seed_area(
    conn: psycopg.Connection[TupleRow],
    *,
    band: int | None = 6,
    family: str = "copper",
    technology: str = "VECT_VDSL",
    scale: float = 1.0,
) -> None:
    """A filed cabinet. `scale` blows it up past the cap, which is what a district is."""
    conn.execute(
        "insert into coverage_area (source, source_ref, provider_id, technology, family, "
        "speed_band_id, assertion, geom) values ('register', %s, %s, %s, %s, %s, 'declared', "
        "st_multi(st_scale(st_transform(st_setsrid(st_geomfromgeojson(%s), 2100), 4326), "
        "st_point(%s, %s), 'POINT(24.005 40.834)'::geometry))::geography)",
        (f"cab-{technology}-{scale}", provider_id(conn), technology, family, band,
         CABINET_2100, scale, scale),
    )
    conn.commit()


def seed_door(conn: psycopg.Connection[TupleRow], *, band: int | None, family: str = "fiber",
              technology: str = "FTTH") -> None:
    """An address on the street, with a filing against it."""
    conn.execute(
        "insert into address (street, street_fold, geom, search_key, latin_key, "
        "municipality_id) values ('ΤΕΣΤ', 'ΤΕΣΤ', 'SRID=4326;POINT(24.0055 40.8345)', "
        "'ΤΕΣΤ', 'TEST', 1)"
    )
    conn.execute(
        "insert into address_coverage (address_id, provider_id, technology, family, "
        "matched_by, speed_band_id, built_by) select a.id, %s, %s, %s, 'point', %s, '050' "
        "from address a where a.street_fold = 'ΤΕΣΤ'",
        (provider_id(conn), technology, family, band),
    )
    conn.commit()


def reach(conn: psycopg.Connection[TupleRow]) -> list[tuple[str, float | None]]:
    rows = conn.execute(
        "select p.code, sp.mbps from street_provider sp "
        "join provider p on p.id = sp.provider_id order by p.code"
    ).fetchall()
    return [(str(code), None if mbps is None else float(mbps)) for code, mbps in rows]


def figure(conn: psycopg.Connection[TupleRow]) -> float | None:
    row = conn.execute("select best_mbps from street").fetchone()
    assert row is not None
    return None if row[0] is None else float(row[0])


def test_a_street_with_no_door_is_reached_by_the_cabinet_it_crosses(
    reachable: psycopg.Connection[TupleRow],
) -> None:
    """Half the streets have no address filed on them and people still live on them.

    Band 6 is "100-300 Mbps" and is worth 100: the band assures its floor, not its ceiling.
    """
    seed_street(reachable)
    seed_area(reachable, band=6)
    run(reachable, steps())
    assert reach(reachable) == [("TEST", 100.0)]


def test_a_street_with_no_door_is_painted_by_it_too(
    reachable: psycopg.Connection[TupleRow],
) -> None:
    """The colour and the filter come from one row, so they cannot disagree."""
    seed_street(reachable)
    seed_area(reachable, band=6)
    run(reachable, steps())
    assert figure(reachable) == 100.0


def test_a_street_outside_the_cabinet_is_reached_by_nobody(
    reachable: psycopg.Connection[TupleRow],
) -> None:
    seed_street(reachable, OUTSIDE_LINE)
    seed_area(reachable, band=6)
    run(reachable, steps())
    assert reach(reachable) == []
    assert figure(reachable) is None


def test_a_door_reaches_a_street_its_cabinets_do_not(
    reachable: psycopg.Connection[TupleRow],
) -> None:
    """Every builder files doors and no polygons; INALAN has 112,739 and not one area."""
    seed_street(reachable)
    seed_door(reachable, band=8)
    run(reachable, steps())
    assert reach(reachable) == [("TEST", 1000.0)]


def test_both_routes_are_asked_and_the_best_wins(
    reachable: psycopg.Connection[TupleRow],
) -> None:
    """The panel has unioned both since "Ask both ways an operator can reach a street"."""
    seed_street(reachable)
    seed_area(reachable, band=6)
    seed_door(reachable, band=8)
    run(reachable, steps())
    assert reach(reachable) == [("TEST", 1000.0)]
    assert figure(reachable) == 1000.0


def test_a_district_sized_filing_does_not_name_a_street(
    reachable: psycopg.Connection[TupleRow],
) -> None:
    """Λίμνης Κορώνειας crosses nothing but three filings of 36.8 km2. It was drawn at 100
    and reported as nothing at all, along with 3,188 others."""
    seed_street(reachable)
    seed_area(reachable, band=6, scale=40.0)
    run(reachable, steps())
    assert reach(reachable) == []
    assert figure(reachable) is None


def test_the_cap_is_the_one_the_panel_uses(db: psycopg.Connection[TupleRow]) -> None:
    """Carried by hand in two files until migration 0046. api/main.py asks for it by name."""
    row = db.execute("select cabinet_m2()").fetchone()
    assert row == (5_000_000.0,)


def test_mobile_does_not_reach_a_street(reachable: psycopg.Connection[TupleRow]) -> None:
    """5G reaches nearly every address and files a 300-1000 band wherever it does. Counted,
    it made 40,775 of the 40,796 streets with a figure come out at exactly 1000."""
    seed_street(reachable)
    seed_door(reachable, band=7, family="wireless", technology="FWA_5G")
    run(reachable, steps())
    assert reach(reachable) == []
    assert figure(reachable) is None


def test_a_withdrawn_filing_stops_reaching_the_street(
    reachable: psycopg.Connection[TupleRow],
) -> None:
    """The step recomputes rather than fills in.

    Both statements used to only ever write a figure, so a street that qualified under a
    looser rule kept what that rule gave it forever.
    """
    street_id = seed_street(reachable)
    seed_area(reachable, band=6)
    run(reachable, steps())
    assert figure(reachable) == 100.0

    reachable.execute("delete from coverage_area")
    reachable.commit()
    run(reachable, steps())
    assert reach(reachable) == []
    assert figure(reachable) is None
    # The street itself is untouched. Only what was claimed about it has gone.
    assert reachable.execute(
        "select count(*) from street where id = %s", (street_id,)
    ).fetchone() == (1,)


def test_rebuilding_does_not_double_the_operators(
    reachable: psycopg.Connection[TupleRow],
) -> None:
    seed_street(reachable)
    seed_area(reachable, band=6)
    seed_door(reachable, band=8)
    run(reachable, steps())
    run(reachable, steps())
    assert reach(reachable) == [("TEST", 1000.0)]


def test_the_figure_is_what_the_line_is_sold_at(
    reachable: psycopg.Connection[TupleRow],
) -> None:
    """Technology is the anchor and the register's own speeds are not consulted.

    Not max_plausible_mbps either, which is a physics ceiling nobody sells: every vectored
    plan in Greece is exactly 100, whatever vectoring is capable of.
    """
    seed_street(reachable)
    seed_area(reachable, band=6, technology="VECT_VDSL")
    run(reachable, steps())
    assert figure(reachable) == 100.0


def test_the_filing_can_lower_the_figure_but_never_lift_it(
    reachable: psycopg.Connection[TupleRow],
) -> None:
    """Technology is the anchor and the filing is a cap on it: least(sold, the band's top).

    An operator filing a low band is telling us this particular line is bad, and that is
    worth more than the national retail figure.
    """
    seed_street(reachable)
    # Band 3 is "2-10 Mbps", below what vectoring retails at, so it pulls the figure down.
    seed_area(reachable, band=3, technology="VECT_VDSL")
    run(reachable, steps())
    assert figure(reachable) == 10.0

    # Band 8 is ">= 1000", far above it, and lifts nothing.
    reachable.execute("delete from coverage_area")
    reachable.commit()
    seed_area(reachable, band=8, technology="VECT_VDSL")
    run(reachable, steps())
    assert figure(reachable) == 100.0


def test_an_unfiled_band_caps_nothing(reachable: psycopg.Connection[TupleRow]) -> None:
    """70.8% of the million fiber filings carry no band, so this is the common path.

    least() ignores nulls, which is the behaviour that quietly invented 24 Mbps out of
    nothing in 130 and is exactly right here: no band filed means nothing caps the line.
    """
    seed_street(reachable)
    seed_area(reachable, band=None, technology="VECT_VDSL")
    run(reachable, steps())
    assert figure(reachable) == 100.0


def test_the_open_topped_band_caps_nothing_either(
    reachable: psycopg.Connection[TupleRow],
) -> None:
    """">= 1000 Mbps" has no ceiling at all, and a null ceiling is not a cap of zero.

    Every fiber filing that carries a band carries this one, so getting it wrong would take
    the whole fiber map to nothing.
    """
    seed_street(reachable)
    seed_door(reachable, band=8, family="fiber", technology="FTTH")
    run(reachable, steps())
    assert figure(reachable) == 1000.0


def test_adsl_is_twenty_four(reachable: psycopg.Connection[TupleRow]) -> None:
    """The register files ADSL at 100-300 Mbps and five rows of it at a gigabit.

    Physically impossible, faithfully carried, and it reached 1,061 ADSL-only streets.
    """
    seed_street(reachable)
    seed_area(reachable, band=6, technology="ADSL")
    run(reachable, steps())
    assert figure(reachable) == 24.0


def test_plain_vdsl_is_fifty(reachable: psycopg.Connection[TupleRow]) -> None:
    """Every VDSL plan on file is 50: Telekom 50, Vodafone 50. Not the 100 the cable can do."""
    seed_street(reachable)
    seed_area(reachable, band=7, technology="VDSL")
    run(reachable, steps())
    assert figure(reachable) == 50.0


def test_fiber_is_a_gigabit(reachable: psycopg.Connection[TupleRow]) -> None:
    """Plans run 100 to 3000, and the register's own top band is open-ended at 1000."""
    seed_street(reachable)
    seed_door(reachable, band=None, family="fiber", technology="FTTH")
    run(reachable, steps())
    assert figure(reachable) == 1000.0


def test_fiber_with_no_band_is_still_fiber(
    reachable: psycopg.Connection[TupleRow],
) -> None:
    """This is the case that made the decision.

    758,885 of 1,071,133 FTTH filings carry no speed band, so 11,880 streets with fiber
    running down them were painted as copper.
    """
    seed_street(reachable)
    seed_area(reachable, band=6, technology="VECT_VDSL")
    seed_door(reachable, band=None, family="fiber", technology="FTTH")
    run(reachable, steps())
    assert figure(reachable) == 1000.0


def test_the_best_line_wins(reachable: psycopg.Connection[TupleRow]) -> None:
    """Fiber beats vectoring beats VDSL beats ADSL, by their own figures rather than by rank."""
    seed_street(reachable)
    for tech in ("ADSL", "VDSL", "VECT_VDSL"):
        seed_area(reachable, band=None, technology=tech)
    run(reachable, steps())
    assert figure(reachable) == 100.0


def test_only_four_figures_are_retailed(reachable: psycopg.Connection[TupleRow]) -> None:
    """The whole set a street can be retailed at, and so the whole set the legend can show.

    A filing can only cap a figure below its line's retail speed, never lift it above, so
    nothing can land in a band higher than one of these.
    """
    sold = reachable.execute(
        "select distinct sold_mbps from technology "
        "where family in ('copper', 'fiber') and sold_mbps is not null order by 1"
    ).fetchall()
    assert [float(row[0]) for row in sold] == [24.0, 50.0, 100.0, 1000.0]
