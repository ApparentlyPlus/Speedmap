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
TABLE = """
<table id="speedTable">
 <tbody id="speed100">
  <tr><td>Ονομαστική</td><td>100</td></tr>
  <tr><td>Λήψη</td><td>104,81</td><td>96,20</td><td>69,64</td></tr>
  <tr><td>Αποστολή</td><td>10,47</td><td>10,10</td><td>9,80</td></tr>
 </tbody>
 <tbody id="speed24">
  <tr><td>Ονομαστική</td><td>24</td></tr>
  <tr><td>Λήψη</td><td>15,22</td><td>11,24</td><td>6,30</td></tr>
  <tr><td>Αποστολή</td><td>0,82</td><td>0,70</td><td>0,41</td></tr>
 </tbody>
</table>
"""

INVESTIGATE = "<div>Απαιτείται περαιτέρω διερεύνηση για τη διαθεσιμότητα στη διεύθυνση</div>"

NAMED = Naming(nomos="ΑΤΤΙΚΗΣ", dimos="ΑΘΗΝΑΙΩΝ", area="ΑΘΗΝΑ-ΠΑΤΗΣΙΑ", street="ΑΧΑΡΝΩΝ")
TARGET = Target(address_id=1, lat=0.0, lon=0.0, street="ΑΧΑΡΝΩΝ", street_no="100",
                municipality="ΔΗΜΟΣ ΑΘΗΝΑΙΩΝ")


@pytest.fixture
def scraped(db: psycopg.Connection[TupleRow]) -> Iterator[psycopg.Connection[TupleRow]]:
    db.execute("truncate raw_cosmote cascade")
    db.commit()
    yield db
    db.execute("truncate raw_cosmote cascade")
    db.commit()


def test_speed_names_the_medium() -> None:
    assert technology_of(1000) == "FTTH"
    assert technology_of(200) == "FTTH"
    assert technology_of(100) == "VECT_VDSL"
    assert technology_of(50) == "VDSL"
    assert technology_of(24) == "ADSL"


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
    assert found["VECT_VDSL"].max_down_mbps == Decimal("104.81")
    assert found["VECT_VDSL"].avg_down_mbps == Decimal("96.20")
    assert found["ADSL"].max_down_mbps == Decimal("15.22")
    assert found["ADSL"].avg_down_mbps == Decimal("11.24")


def test_an_empty_table_offers_nothing() -> None:
    assert offers("<table id='speedTable'></table>") == ()
    assert read("<html></html>").serviceable is False


def test_their_hierarchy_is_read_back_not_reconstructed(
    scraped: psycopg.Connection[TupleRow],
) -> None:
    """Only 164 of their 506 municipalities share a name with a Καλλικράτης one."""
    scraped.execute(
        "insert into raw_cosmote (id, nomos, dimos, area, street, street_no, plans, "
        "observed_at, municipality_id, street_fold) values (1, 'ΑΤΤΙΚΗΣ', 'ΑΘΗΝΑΙΩΝ', "
        "'ΑΘΗΝΑ-ΠΑΤΗΣΙΑ', 'ΑΧΑΡΝΩΝ', 100, 'FBR_1G', '2026-08-06', null, 'ΑΧΑΡΝΩΝ')"
    )
    scraped.commit()
    assert naming(scraped, 0, "ΑΧΑΡΝΩΝ") is None
    found = scraped.execute(
        "select nomos, dimos, area, street from raw_cosmote where street_fold = 'ΑΧΑΡΝΩΝ'"
    ).fetchone()
    assert found == ("ΑΤΤΙΚΗΣ", "ΑΘΗΝΑΙΩΝ", "ΑΘΗΝΑ-ΠΑΤΗΣΙΑ", "ΑΧΑΡΝΩΝ")


def test_the_form_carries_their_prefixes() -> None:
    """Their fields want Ν. and Δ. in front, which is why our names alone do not work."""
    form = Cosmote().form(TARGET, NAMED)
    assert form["mState"] == "Ν. ΑΤΤΙΚΗΣ"
    assert form["mPrefecture"] == "Δ. ΑΘΗΝΑΙΩΝ"
    assert form["mArea"] == "ΑΘΗΝΑ-ΠΑΤΗΣΙΑ"
    assert form["mAddress"] == "ΑΧΑΡΝΩΝ"
    assert form["mNumber"] == "100"


def test_a_street_with_no_area_falls_back_to_the_municipality() -> None:
    """Their own form does the same when the area dropdown comes back empty."""
    bare = Naming(nomos="ΑΤΤΙΚΗΣ", dimos="ΑΘΗΝΑΙΩΝ", area=None, street="ΑΧΑΡΝΩΝ")
    assert Cosmote().form(TARGET, bare)["mArea"] == "ΑΘΗΝΑΙΩΝ"
