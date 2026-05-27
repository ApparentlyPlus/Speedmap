"""Asking Cosmote, and being told to look into it by hand."""

from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal

import psycopg
import pytest
from psycopg.rows import TupleRow

from probe.adapter import Target
from probe.cosmote import Cosmote, Naming, naming, offers, read, technology_of

# As their estimate table is built: one tbody per nominal rung, download on the second row
# and upload on the third, each a label followed by maximum, usual and minimum.
# Copied from a live answer. The first four-cell row is a header whose cells read
# Μέγιστη, Συνήθης, Ελάχιστη, and reading it as a measurement is the mistake this shape
# exists to catch.
TABLE = """
<table id="speedTable">
 <tbody style="display: none;" id="speed24">
  <tr><td>Tαχύτητα</td><td>Μέγιστη</td>
      <td><strong>Συνήθης</strong></td><td>Ελάχιστη</td></tr>
  <tr><td>Download (Mbps)</td><td>18.09</td><td>12.01</td><td>5.08</td></tr>
  <tr><td>Upload (Mbps)</td><td>0.93</td><td>0.85</td><td>0.42</td></tr>
 </tbody>
 <tbody style="display: none;" id="speed50">
  <tr><td>Tαχύτητα</td><td>Μέγιστη</td>
      <td><strong>Συνήθης</strong></td><td>Ελάχιστη</td></tr>
  <tr><td>Download (Mbps)</td><td>50</td><td>28.15</td><td>18</td></tr>
  <tr><td>Upload (Mbps)</td><td>5</td><td>4.55</td><td>0.97</td></tr>
 </tbody>
</table>
"""

INVESTIGATE = "<div>Απαιτείται περαιτέρω διερεύνηση για τη διαθεσιμότητα στη διεύθυνση</div>"

NAMED = Naming(nomos="ΑΤΤΙΚΗΣ", dimos="ΑΘΗΝΑΙΩΝ", area="ΑΘΗΝΑ-ΠΑΤΗΣΙΑ",
               street="ΑΧΑΡΝΩΝ", street_type="ΟΔΟΣ")
TARGET = Target(address_id=1, lat=0.0, lon=0.0, street="ΑΧΑΡΝΩΝ", street_no="100",
                municipality="ΔΗΜΟΣ ΑΘΗΝΑΙΩΝ")


@pytest.fixture
def scraped(db: psycopg.Connection[TupleRow]) -> Iterator[psycopg.Connection[TupleRow]]:
    db.execute("truncate raw_cosmote, municipality cascade")
    db.execute(
        "insert into municipality (id, name, geom) values (1, 'ΔΗΜΟΣ ΑΘΗΝΑΙΩΝ', "
        "st_setsrid(st_geomfromtext('MULTIPOLYGON(((23 37, 24 37, 24 38, 23 37)))'), 4326))"
    )
    db.commit()
    yield db
    db.execute("truncate raw_cosmote, municipality cascade")
    db.commit()


def test_speed_names_the_medium() -> None:
    assert technology_of(1000) == "FTTH"
    assert technology_of(200) == "FTTH"
    assert technology_of(100) == "VECT_VDSL"
    assert technology_of(50) == "VDSL"
    assert technology_of(24) == "ADSL"


def test_thirty_over_copper_is_not_adsl() -> None:
    """ADSL cannot pass 24, which the technology table records as its ceiling."""
    assert technology_of(30) == "VDSL"
    assert technology_of(25) == "VDSL"


def test_being_told_to_investigate_is_not_a_refusal() -> None:
    """Neither yes nor no. Cached as either, it would be repeated for six months."""
    probed = read(INVESTIGATE)
    assert probed.serviceable is False
    assert probed.conclusive is False


def test_a_real_answer_is_conclusive() -> None:
    probed = read(TABLE)
    assert probed.conclusive is True
    assert probed.serviceable is True


def test_each_rung_is_read_with_its_estimate() -> None:
    """The usual speed is what the line carries; the maximum is what the advert says."""
    found = {o.technology: o for o in offers(TABLE)}
    assert found["ADSL"].max_down_mbps == Decimal("18.09")
    assert found["ADSL"].avg_down_mbps == Decimal("12.01")
    assert found["ADSL"].avg_up_mbps == Decimal("0.85")
    assert found["VDSL"].max_down_mbps == Decimal("50")
    assert found["VDSL"].avg_down_mbps == Decimal("28.15")


def test_an_empty_table_offers_nothing() -> None:
    assert offers("<table id='speedTable'></table>") == ()
    assert read("<html></html>").serviceable is False


def test_their_hierarchy_is_read_back_not_reconstructed(
    scraped: psycopg.Connection[TupleRow],
) -> None:
    """Only 164 of their 506 municipalities share a name with a Καλλικράτης one."""
    scraped.execute(
        "insert into raw_cosmote (id, nomos, dimos, area, street_type, street, street_no, "
        "plans, observed_at, municipality_id, street_fold) values (1, 'ΑΤΤΙΚΗΣ', 'ΑΘΗΝΑΙΩΝ', "
        "'ΑΘΗΝΑ-ΠΑΤΗΣΙΑ', 'ΟΔΟΣ', 'ΑΧΑΡΝΩΝ', 100, 'FBR_1G', '2026-08-06', 1, 'ΑΧΑΡΝΩΝ')"
    )
    scraped.commit()
    assert naming(scraped, 999, "ΑΧΑΡΝΩΝ") is None
    found = naming(scraped, 1, "ΑΧΑΡΝΩΝ")
    assert found == NAMED


def test_the_form_carries_their_prefixes() -> None:
    """Their fields want Ν. and Δ. in front, which is why our names alone do not work."""
    form = Cosmote().form(TARGET, NAMED)
    assert form["mState"] == "Ν. ΑΤΤΙΚΗΣ"
    assert form["mPrefecture"] == "Δ. ΑΘΗΝΑΙΩΝ"
    assert form["mArea"] == "ΑΘΗΝΑ-ΠΑΤΗΣΙΑ"
    assert form["mAddress"] == "ΑΧΑΡΝΩΝ (ΟΔΟΣ)"
    assert form["mNumber"] == "100"


def test_a_street_with_no_area_falls_back_to_the_municipality() -> None:
    """Their own form does the same when the area dropdown comes back empty."""
    bare = Naming(nomos="ΑΤΤΙΚΗΣ", dimos="ΑΘΗΝΑΙΩΝ", area=None,
                  street="ΑΧΑΡΝΩΝ", street_type="ΟΔΟΣ")
    assert Cosmote().form(TARGET, bare)["mArea"] == "ΑΘΗΝΑΙΩΝ"


def test_the_street_type_is_what_makes_them_answer() -> None:
    """A bare name is told to be investigated by hand, whatever else the request gets right."""
    assert Cosmote().addressed(NAMED) == "ΑΧΑΡΝΩΝ (ΟΔΟΣ)"


def test_a_street_with_no_recorded_type_is_sent_bare() -> None:
    """Better a name they may refuse than a type invented for them."""
    untyped = Naming(nomos="ΑΤΤΙΚΗΣ", dimos="ΑΘΗΝΑΙΩΝ", area=None,
                     street="ΑΧΑΡΝΩΝ", street_type=None)
    assert Cosmote().addressed(untyped) == "ΑΧΑΡΝΩΝ"


def test_the_header_row_is_not_a_measurement() -> None:
    """Its cells read Μέγιστη, Συνήθης, Ελάχιστη. Read as numbers they are silently None."""
    from probe.cosmote import SpeedTable, line

    table = SpeedTable()
    table.feed(TABLE)
    header = table.rows[24][0]
    assert header[1].startswith("Μέγ")
    assert line(table.rows[24], "DOWNLOAD") == ["Download (Mbps)", "18.09", "12.01", "5.08"]
