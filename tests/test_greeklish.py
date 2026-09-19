"""Transliteration, and the Greeklish spellings people actually type."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from normalise.greeklish import from_greek, from_latin, is_greeklish
from normalise.text import strip_marks

# Greek name, then spellings a user might type. Marked exact where the two forms must be
# identical. The rest are close enough for the trigram index to find.
EXACT = [
    ("ΑΧΑΡΝΩΝ", ["axarnon", "acharnon", "aharnon", "AXARNON"]),
    ("ΤΖΕΛΙΛΗ", ["tzelili"]),
    ("ΘΕΣΣΑΛΟΝΙΚΗΣ", ["thessalonikis", "8essalonikis", "9essalonikis"]),
    ("ΑΓΙΟΥ ΙΩΑΝΝΟΥ", ["agiou ioannou", "agiu ioannu"]),
    ("ΗΛΙΑ", ["ilia"]),
    ("ΑΛΕΞΑΝΔΡΑΣ", ["alexandras", "aleksandras"]),
    ("ΕΥΑΓΓΕΛΙΣΤΡΙΑΣ", ["evangelistrias"]),
    ("ΑΥΛΩΝΟΣ", ["avlonos"]),
    ("ΕΥΤΥΧΙΑ", ["eftixia"]),
    ("ΜΠΟΤΣΑΡΗ", ["botsari", "mpotsari"]),
    ("ΝΤΟΥΝΤΟΥ", ["dudu", "ntountou"]),
]


@pytest.mark.parametrize(("greek", "spellings"), EXACT)
def test_greeklish_reaches_the_same_form(greek: str, spellings: list[str]) -> None:
    target = from_greek(greek)
    for spelling in spellings:
        assert from_latin(spelling) == target, spelling


@pytest.mark.parametrize(
    ("greek", "latin"),
    [
        ("ΑΧΑΡΝΩΝ", "AXARNON"),
        ("ΑΛΕΞΑΝΔΡΑΣ", "ALEXANDRAS"),
        ("ΨΑΡΩΝ", "PSARON"),
        ("ΕΥΑΓΓΕΛΙΣΤΡΙΑΣ", "EVANGELISTRIAS"),
        ("ΑΥΛΩΝΟΣ", "AVLONOS"),
        ("ΟΔΥΣΣΕΩΣ", "ODISSEOS"),
    ],
)
def test_greek_transliterates_predictably(greek: str, latin: str) -> None:
    assert from_greek(greek) == latin


def test_theta_survives_the_h_rule() -> None:
    """A lone H becomes Χ, so TH must be held aside or ΘΕΣΣΑΛΟΝΙΚΗ becomes ΤΧΕΣ..."""
    assert from_latin("thessaloniki").startswith("THES")
    assert from_greek("ΘΕΣΣΑΛΟΝΙΚΗ").startswith("THES")


def test_a_lone_h_is_chi_not_eta() -> None:
    """aharnon is far more common than hlias, and the trigram fallback covers the rest."""
    assert from_latin("aharnon") == from_greek("ΑΧΑΡΝΩΝ")
    assert from_latin("hlia") != from_greek("ΗΛΙΑ")


def test_no_greek_survives_transliteration() -> None:
    for greek, _ in EXACT:
        assert not any("Ͱ" <= c <= "Ͽ" for c in from_greek(greek))


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("axarnon", True),
        ("ΑΧΑΡΝΩΝ", False),
        ("Αχαρνών", False),
        ("agiou ioannou", True),
        ("8essalonikis", True),
        ("123", False),
        ("", False),
        ("ΑΧΑΡΝΩΝ 12", False),
    ],
)
def test_greeklish_is_detected(query: str, expected: bool) -> None:
    assert is_greeklish(query) is expected


@given(st.text())
def test_transliteration_never_raises(text: str) -> None:
    assert isinstance(from_greek(text), str)
    assert isinstance(from_latin(text), str)


@given(st.text())
def test_transliteration_leaves_no_combining_marks(text: str) -> None:
    assert from_greek(text) == from_greek(strip_marks(text))


@pytest.mark.parametrize(
    ("greek", "latin"),
    [
        ("ΑΥΛΩΝΟΣ", "AVLONOS"),
        ("ΑΥΓΗΣ", "AVGIS"),
        ("ΕΥΖΩΝΩΝ", "EVZONON"),
        ("ΕΥΡΙΠΙΔΟΥ", "EVRIPIDU"),
        ("ΕΥΤΥΧΙΑ", "EFTIXIA"),
        ("ΕΥΞΕΙΝΟΥ", "EFXINU"),
    ],
)
def test_upsilon_pairs_voice_by_what_follows(greek: str, latin: str) -> None:
    """ΑΥ and ΕΥ are av/ev before a vowel or voiced consonant, af/ef before a voiceless one."""
    assert from_greek(greek) == latin


def test_double_gamma_stays_distinct_from_single() -> None:
    """ΓΓ is /ng/, so ΑΓΓΕΛΟΣ is angelos. Mapping it to g would merge it with ΑΓΕΛΟΣ."""
    assert from_greek("ΑΓΓΕΛΟΣ") == "ANGELOS"
    assert from_greek("ΑΓΕΛΟΣ") == "AGELOS"
    assert from_latin("angelos") == from_greek("ΑΓΓΕΛΟΣ")


def test_doubled_consonants_are_kept() -> None:
    """ΑΛΛΟΣ and ΑΛΟΣ stay apart. A user typing either is bridged by the trigram index."""
    assert from_greek("ΑΛΛΟΣ") != from_greek("ΑΛΟΣ")


def test_xi_and_chi_share_a_letter() -> None:
    """Both are written x in practice, and merging them collides nothing in 30,272 names."""
    assert from_greek("ΑΛΕΞΑΝΔΡΑΣ") == "ALEXANDRAS"
    assert from_latin("alexandras") == from_latin("aleksandras")
