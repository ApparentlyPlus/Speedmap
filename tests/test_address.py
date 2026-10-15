from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from normalise.address import ParsedAddress, parse, parse_part

CORNER = (
    "26332,ΠΑΡΟΔΟΣ ΑΝΑΓΝΩΣΤΟΥ ΣΤΑΥΡΟΠΟΥΛΟΥ 10,10,Δ. ΠΑΤΡΕΩΝ"
    "|26332,ΑΝΑΓΝΩΣΤΟΥ ΣΤΑΥΡΟΠΟΥΛΟΥ,10,Δ. ΠΑΤΡΕΩΝ"
)


def _one(raw: str) -> ParsedAddress:
    addresses = parse(raw)
    assert len(addresses) == 1
    return addresses[0]


def test_parse() -> None:
    a = _one("56429,Αμυγδαλιάς,11,ΕΥΚΑΡΠΙΑ")
    assert a.postcode == "56429"
    assert a.street == "Αμυγδαλιάς"
    assert a.street_no == "11"
    assert a.locality == "ΕΥΚΑΡΠΙΑ"
    assert a.search_key == "ΑΜΥΓΔΑΛΙΑΣ ΕΥΚΑΡΠΙΑ"

    # corner building, filed under both streets
    addresses = parse(CORNER)
    assert [a.street for a in addresses] == ["ΠΑΡΟΔΟΣ ΑΝΑΓΝΩΣΤΟΥ ΣΤΑΥΡΟΠΟΥΛΟΥ 10", "ΑΝΑΓΝΩΣΤΟΥ ΣΤΑΥΡΟΠΟΥΛΟΥ"]
    assert {a.street_no for a in addresses} == {"10"}

    assert _one("30300,ΝΑΥΠΑΚΤΟΣ, ,Δ. ΝΑΥΠΑΚΤΟΥ").locality == "ΝΑΥΠΑΚΤΟΥ"
    assert _one("54250,Ηγελόχου,14-16,ΘΕΣΣΑΛΟΝΙΚΗ").locality == "ΘΕΣΣΑΛΟΝΙΚΗ"
    assert _one("30300,ΝΑΥΠΑΚΤΟΣ, ,Δ. ΝΑΥΠΑΚΤΟΥ").street_no is None
    assert _one("15123,ΛΕΩΦΟΡΟΣ ΙΩΑΝΝΗ ΚΑΠΟΔΙΣΤΡΙΟΥ,18,Δ. ΑΜΑΡΟΥΣΙΟΥ").search_key == "ΙΩΑΝΝΗ ΚΑΠΟΔΙΣΤΡΙΟΥ ΑΜΑΡΟΥΣΙΟΥ"
    key = _one("58200,ΠΑΡΟΔΟΣ ΑΓΙΟΥ ΔΗΜΗΤΡΙΟΥ,33,Δ. ΕΔΕΣΣΑΣ").search_key
    assert key.startswith("ΠΑΡΟΔΟΣ ")


def test_parse_numbers() -> None:
    for raw, expected in [
        ("54250,Ηγελόχου,14-16,ΘΕΣΣΑΛΟΝΙΚΗ", "14-16"),
        ("14341,Πριγκίπου,9Β,ΝΕΑ ΦΙΛΑΔΕΛΦΕΙΑ", "9Β"),
        ("54250,Γενοκτονίας 19ης Μαΐου,2M4,ΘΕΣΣΑΛΟΝΙΚΗ", "2M4"),
        ("59200,Α' ΠΑΡΟΔΟΣ ΑΡΙΣΤΕΙΔΗ ΚΟΚΚΙΝΟΥ,9-11,Δ. ΝΑΟΥΣΑΣ", "9-11"),
    ]:
        assert _one(raw).street_no == expected

    # ~1 row in 3000 has a one character postcode
    assert _one("5,Αμυγδαλιάς,11,ΕΥΚΑΡΠΙΑ").postcode is None
    assert _one("ABCDE,Αμυγδαλιάς,11,ΕΥΚΑΡΠΙΑ").postcode is None


def test_parse_bad() -> None:
    for raw in [
        "",
        "not an address",
        "56429,Αμυγδαλιάς,11",
        "56429,Αμυγδαλιάς,11,ΕΥΚΑΡΠΙΑ,extra",
        "56429, ,11,ΕΥΚΑΡΠΙΑ",
    ]:
        assert parse(raw) == []
    assert [a.street for a in parse("56429,Αμυγδαλιάς,11,ΕΥΚΑΡΠΙΑ|garbage")] == ["Αμυγδαλιάς"]
    assert parse_part("56431,,1,ΣΤΑΥΡΟΥΠΟΛΗ") is None


@given(st.text())
def test_parse_anything(raw: str) -> None:
    for a in parse(raw):
        assert a.street.strip() == a.street
        assert a.street != ""
