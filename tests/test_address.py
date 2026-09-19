"""Parsing the register's packed address field, against real values."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from normalise.address import ParsedAddress, parse, parse_part

CORNER = (
    "26332,ΠΑΡΟΔΟΣ ΑΝΑΓΝΩΣΤΟΥ ΣΤΑΥΡΟΠΟΥΛΟΥ 10,10,Δ. ΠΑΤΡΕΩΝ"
    "|26332,ΑΝΑΓΝΩΣΤΟΥ ΣΤΑΥΡΟΠΟΥΛΟΥ,10,Δ. ΠΑΤΡΕΩΝ"
)


def one(raw: str) -> ParsedAddress:
    addresses = parse(raw)
    assert len(addresses) == 1
    return addresses[0]


def test_the_four_fields_are_read() -> None:
    address = one("56429,Αμυγδαλιάς,11,ΕΥΚΑΡΠΙΑ")
    assert address.postcode == "56429"
    assert address.street == "Αμυγδαλιάς"
    assert address.street_no == "11"
    assert address.locality == "ΕΥΚΑΡΠΙΑ"


def test_a_corner_building_yields_both_addresses() -> None:
    """6.43% of points are filed under more than one street. Dropping one loses a real address."""
    addresses = parse(CORNER)
    assert [a.street for a in addresses] == [
        "ΠΑΡΟΔΟΣ ΑΝΑΓΝΩΣΤΟΥ ΣΤΑΥΡΟΠΟΥΛΟΥ 10",
        "ΑΝΑΓΝΩΣΤΟΥ ΣΤΑΥΡΟΠΟΥΛΟΥ",
    ]
    assert {a.street_no for a in addresses} == {"10"}


def test_locality_prefix_is_dropped() -> None:
    assert one("30300,ΝΑΥΠΑΚΤΟΣ, ,Δ. ΝΑΥΠΑΚΤΟΥ").locality == "ΝΑΥΠΑΚΤΟΥ"


def test_locality_without_a_prefix_is_untouched() -> None:
    assert one("54250,Ηγελόχου,14-16,ΘΕΣΣΑΛΟΝΙΚΗ").locality == "ΘΕΣΣΑΛΟΝΙΚΗ"


# street numbers.


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("54250,Ηγελόχου,14-16,ΘΕΣΣΑΛΟΝΙΚΗ", "14-16"),
        ("14341,Πριγκίπου,9Β,ΝΕΑ ΦΙΛΑΔΕΛΦΕΙΑ", "9Β"),
        ("54250,Γενοκτονίας 19ης Μαΐου,2M4,ΘΕΣΣΑΛΟΝΙΚΗ", "2M4"),
        ("59200,Α' ΠΑΡΟΔΟΣ ΑΡΙΣΤΕΙΔΗ ΚΟΚΚΙΝΟΥ,9-11,Δ. ΝΑΟΥΣΑΣ", "9-11"),
    ],
)
def test_street_numbers_are_kept_verbatim(raw: str, expected: str) -> None:
    """Ranges and letter suffixes are real numbers, not values to be normalised away."""
    assert one(raw).street_no == expected


def test_a_blank_number_is_absent_not_empty() -> None:
    """The register writes a single space when there is no number."""
    assert one("30300,ΝΑΥΠΑΚΤΟΣ, ,Δ. ΝΑΥΠΑΚΤΟΥ").street_no is None


# postcodes.


def test_a_malformed_postcode_becomes_unknown() -> None:
    """One row in 3000 has a one-character postcode. Unknown is honest. Repaired is not."""
    assert one("5,Αμυγδαλιάς,11,ΕΥΚΑΡΠΙΑ").postcode is None


def test_a_non_numeric_postcode_becomes_unknown() -> None:
    assert one("ABCDE,Αμυγδαλιάς,11,ΕΥΚΑΡΠΙΑ").postcode is None


# search key.


def test_search_key_folds_street_and_locality() -> None:
    assert one("56429,Αμυγδαλιάς,11,ΕΥΚΑΡΠΙΑ").search_key == "ΑΜΥΓΔΑΛΙΑΣ ΕΥΚΑΡΠΙΑ"


def test_search_key_drops_the_street_type_word() -> None:
    assert one("15123,ΛΕΩΦΟΡΟΣ ΙΩΑΝΝΗ ΚΑΠΟΔΙΣΤΡΙΟΥ,18,Δ. ΑΜΑΡΟΥΣΙΟΥ").search_key == (
        "ΙΩΑΝΝΗ ΚΑΠΟΔΙΣΤΡΙΟΥ ΑΜΑΡΟΥΣΙΟΥ"
    )


def test_search_key_keeps_parodos() -> None:
    key = one("58200,ΠΑΡΟΔΟΣ ΑΓΙΟΥ ΔΗΜΗΤΡΙΟΥ,33,Δ. ΕΔΕΣΣΑΣ").search_key
    assert key.startswith("ΠΑΡΟΔΟΣ ")


# malformed input.


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "not an address",
        "56429,Αμυγδαλιάς,11",
        "56429,Αμυγδαλιάς,11,ΕΥΚΑΡΠΙΑ,extra",
        "56429, ,11,ΕΥΚΑΡΠΙΑ",
    ],
)
def test_unparsable_parts_are_dropped(raw: str) -> None:
    """A shape we do not recognise yields nothing rather than a half-built address."""
    assert parse(raw) == []


def test_one_bad_part_does_not_lose_the_good_one() -> None:
    raw = "56429,Αμυγδαλιάς,11,ΕΥΚΑΡΠΙΑ|garbage"
    assert [a.street for a in parse(raw)] == ["Αμυγδαλιάς"]


def test_a_point_filed_without_a_street_yields_no_address() -> None:
    """Real, and about 1 row in 2000. The point keeps its geometry. It just has no address."""
    assert parse_part("56431,,1,ΣΤΑΥΡΟΥΠΟΛΗ") is None


@given(st.text())
def test_parsing_never_raises(raw: str) -> None:
    for address in parse(raw):
        assert address.street.strip() == address.street
        assert address.street != ""
