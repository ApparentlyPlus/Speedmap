from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from normalise.greeklish import from_greek, from_latin, is_greeklish
from normalise.text import strip_marks

# spellings that have to land exactly, the trigram index finds the rest
EXACT = [
    ("ΑΧΑΡΝΩΝ", ["axarnon", "acharnon", "aharnon", "AXARNON"]),
    ("ΤΖΕΛΙΛΗ", ["tzelili"]),
    ("ΘΕΣΣΑΛΟΝΙΚΗΣ", ["thessalonikis", "8essalonikis", "9essalonikis"]),
    ("ΑΓΙΟΥ ΙΩΑΝΝΟΥ", ["agiou ioannou", "agiu ioannu"]),
    ("ΗΛΙΑ", ["ilia"]),
    ("ΑΛΕΞΑΝΔΡΑΣ", ["alexandras", "aleksandras"]),
    ("ΕΥΑΓΓΕΛΙΣΤΡΙΑΣ", ["evangelistrias", "evaggelistrias"]),
    ("ΑΓΓΕΛΟΥ", ["aggelou", "angelou"]),
    ("ΑΥΛΩΝΟΣ", ["avlonos"]),
    ("ΕΥΤΥΧΙΑ", ["eftixia"]),
    ("ΜΠΟΤΣΑΡΗ", ["botsari", "mpotsari"]),
    ("ΝΤΟΥΝΤΟΥ", ["dudu", "ntountou"]),
]


def test_from_latin() -> None:
    for greek, spellings in EXACT:
        target = from_greek(greek)
        for spelling in spellings:
            assert from_latin(spelling) == target, spelling

    assert from_latin("thessaloniki").startswith("THES")
    # lone H is Χ
    assert from_latin("aharnon") == from_greek("ΑΧΑΡΝΩΝ")
    assert from_latin("hlia") != from_greek("ΗΛΙΑ")
    assert from_latin("angelos") == from_greek("ΑΓΓΕΛΟΣ")
    assert from_latin("alexandras") == from_latin("aleksandras")

    # a house number is not a θ
    assert from_latin("ermou 18") == "ERMU 18"
    assert from_latin("ermou 9a") == "ERMU 9A"
    assert from_latin("8eotokou 9") == from_greek("ΘΕΟΤΟΚΟΥ") + " 9"


def test_from_greek() -> None:
    for greek, latin in [
        ("ΑΧΑΡΝΩΝ", "AXARNON"),
        ("ΑΛΕΞΑΝΔΡΑΣ", "ALEXANDRAS"),
        ("ΨΑΡΩΝ", "PSARON"),
        ("ΕΥΑΓΓΕΛΙΣΤΡΙΑΣ", "EVANGELISTRIAS"),
        ("ΑΥΛΩΝΟΣ", "AVLONOS"),
        ("ΟΔΥΣΣΕΩΣ", "ODISSEOS"),
    ]:
        assert from_greek(greek) == latin
    assert from_greek("ΘΕΣΣΑΛΟΝΙΚΗ").startswith("THES")
    for greek, _ in EXACT:
        assert not any("Ͱ" <= c <= "Ͽ" for c in from_greek(greek))

    # av/ev before a vowel or voiced consonant, af/ef otherwise
    for greek, latin in [
        ("ΑΥΛΩΝΟΣ", "AVLONOS"),
        ("ΑΥΓΗΣ", "AVGIS"),
        ("ΕΥΖΩΝΩΝ", "EVZONON"),
        ("ΕΥΡΙΠΙΔΟΥ", "EVRIPIDU"),
        ("ΕΥΤΥΧΙΑ", "EFTIXIA"),
        ("ΕΥΞΕΙΝΟΥ", "EFXINU"),
    ]:
        assert from_greek(greek) == latin

    assert from_greek("ΑΓΓΕΛΟΣ") == "ANGELOS"
    assert from_greek("ΑΓΕΛΟΣ") == "AGELOS"
    assert from_greek("ΑΛΛΟΣ") != from_greek("ΑΛΟΣ")
    assert from_greek("ΑΛΕΞΑΝΔΡΑΣ") == "ALEXANDRAS"


def test_is_greeklish() -> None:
    for query, expected in [
        ("axarnon", True),
        ("ΑΧΑΡΝΩΝ", False),
        ("Αχαρνών", False),
        ("agiou ioannou", True),
        ("8essalonikis", True),
        ("123", False),
        ("", False),
        ("ΑΧΑΡΝΩΝ 12", False),
    ]:
        assert is_greeklish(query) is expected


@given(st.text())
def test_transliterate_anything(text: str) -> None:
    assert isinstance(from_greek(text), str)
    assert isinstance(from_latin(text), str)
    assert from_greek(text) == from_greek(strip_marks(text))
