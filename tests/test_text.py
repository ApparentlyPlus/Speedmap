"""Greek folding: accents, final sigma, and the type words that must not be stripped."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from normalise.text import IDENTITY_WORDS, TYPE_WORDS, fold, street_key

# Real addresses from the register, kept verbatim as fixtures.
REGISTER_SAMPLES = [
    "Α' ΠΑΡΟΔΟΣ ΑΡΙΣΤΕΙΔΗ ΚΟΚΚΙΝΟΥ",
    "Γ' ΠΑΡΟΔΟΣ ΝΙΚΟΛΑΟΥ ΑΝΑΔΟΛΗ",
    "ΠΑΡΟΔΟΣ ΑΝΑΓΝΩΣΤΟΥ ΣΤΑΥΡΟΠΟΥΛΟΥ 10",
    "ΠΛΑΤΕΙΑ ΒΑΣΙΛΕΩΣ ΓΕΩΡΓΙΟΥ Β'",
    "ΛΕΩΦΟΡΟΣ ΙΩΑΝΝΗ ΚΑΠΟΔΙΣΤΡΙΟΥ",
    "Α' ΑΔΙΕΞΟΔΟΣ ΜΑΡΑΣΛΗ",
    "2Η ΠΑΡΟΔΟΣ ΣΚΡΑ",
    "Αχαρνών",
    "Αγίου Ιωάννου",
]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Αχαρνών", "ΑΧΑΡΝΩΝ"),
        ("Αγίου Ιωάννου", "ΑΓΙΟΥ ΙΩΑΝΝΟΥ"),
        ("Ελλησπόντου", "ΕΛΛΗΣΠΟΝΤΟΥ"),
        ("ΑΧΑΡΝΩΝ", "ΑΧΑΡΝΩΝ"),
    ],
)
def test_accents_fold_away(raw: str, expected: str) -> None:
    assert fold(raw) == expected


def test_final_sigma_folds_with_medial_sigma() -> None:
    """Οδός and ΟΔΟΣ are the same word; upper() handles ς, the accent strip handles ό."""
    assert fold("Οδός") == fold("ΟΔΟΣ") == "ΟΔΟΣ"


def test_dialytika_and_tonos_both_go() -> None:
    assert fold("Αϊβαλίου") == "ΑΙΒΑΛΙΟΥ"


def test_whitespace_is_collapsed() -> None:
    assert fold("  ΑΓΙΟΥ   ΙΩΑΝΝΟΥ \n") == "ΑΓΙΟΥ ΙΩΑΝΝΟΥ"


def test_apostrophe_variants_unify() -> None:
    """The register mixes quote characters; Α' and Α’ are the same ordinal."""
    assert fold("Α’ ΠΑΡΟΔΟΣ") == fold("Α' ΠΑΡΟΔΟΣ") == "Α' ΠΑΡΟΔΟΣ"


# type words


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("ΟΔΟΣ ΑΧΑΡΝΩΝ", "ΑΧΑΡΝΩΝ"),
        ("ΛΕΩΦΟΡΟΣ ΙΩΑΝΝΗ ΚΑΠΟΔΙΣΤΡΙΟΥ", "ΙΩΑΝΝΗ ΚΑΠΟΔΙΣΤΡΙΟΥ"),
        ("ΛΕΩΦ. ΑΛΕΞΑΝΔΡΑΣ", "ΑΛΕΞΑΝΔΡΑΣ"),
        ("Λεωφόρου Κηφισίας", "ΚΗΦΙΣΙΑΣ"),
    ],
)
def test_type_words_are_dropped(raw: str, expected: str) -> None:
    assert street_key(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "ΠΑΡΟΔΟΣ ΑΧΑΡΝΩΝ",
        "Α' ΠΑΡΟΔΟΣ ΔΗΜΟΣΘΕΝΟΥΣ",
        "ΠΛΑΤΕΙΑ ΜΑΚΑΡΙΟΥ",
        "ΠΑΡΟΔΟΥ ΑΓΙΟΥ ΔΗΜΗΤΡΙΟΥ",
        "Α' ΑΔΙΕΞΟΔΟΣ ΜΑΡΑΣΛΗ",
        "2Η ΠΑΡΟΔΟΣ ΣΚΡΑ",
    ],
)
def test_identity_words_survive(raw: str) -> None:
    """ΠΑΡΟΔΟΣ ends in ΟΔΟΣ: substring stripping would merge distinct streets."""
    assert street_key(raw) == fold(raw)


def test_parodos_stays_distinct_from_the_street_it_references() -> None:
    """The failure this rule exists to prevent: two different places, one key."""
    assert street_key("ΠΑΡΟΔΟΣ ΑΧΑΡΝΩΝ") != street_key("ΟΔΟΣ ΑΧΑΡΝΩΝ")


def test_numeric_ordinals_are_kept_too() -> None:
    """2Η ΠΑΡΟΔΟΣ and 3Η ΠΑΡΟΔΟΣ of one street are two streets."""
    assert street_key("2Η ΠΑΡΟΔΟΣ ΣΚΡΑ") != street_key("3Η ΠΑΡΟΔΟΣ ΣΚΡΑ")


def test_ordinal_parodoi_stay_distinct() -> None:
    """Α' and Γ' ΠΑΡΟΔΟΣ of the same street are different streets."""
    assert street_key("Α' ΠΑΡΟΔΟΣ ΔΗΜΟΣΘΕΝΟΥΣ") != street_key("Γ' ΠΑΡΟΔΟΣ ΔΗΜΟΣΘΕΝΟΥΣ")


def test_a_name_of_only_type_words_is_not_emptied() -> None:
    """An empty key would match every address in the country."""
    assert street_key("ΟΔΟΣ") == "ΟΔΟΣ"


def test_the_two_word_lists_never_overlap() -> None:
    assert not (TYPE_WORDS & IDENTITY_WORDS)


# properties


@given(st.text())
def test_fold_is_idempotent(text: str) -> None:
    assert fold(fold(text)) == fold(text)


@given(st.text())
def test_street_key_is_idempotent(text: str) -> None:
    assert street_key(street_key(text)) == street_key(text)


@given(st.text(min_size=1).filter(lambda s: s.strip()))
def test_folding_never_empties_a_non_blank_name(text: str) -> None:
    assert street_key(text) != ""


@given(st.text())
def test_fold_leaves_no_combining_marks(text: str) -> None:
    import unicodedata

    assert not any(unicodedata.combining(c) for c in fold(text))


@pytest.mark.parametrize("sample", REGISTER_SAMPLES)
def test_real_register_names_round_trip(sample: str) -> None:
    key = street_key(sample)
    assert key == street_key(key)
    assert key.strip() == key
