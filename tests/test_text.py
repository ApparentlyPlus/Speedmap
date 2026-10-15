from __future__ import annotations

import unicodedata

from hypothesis import given
from hypothesis import strategies as st

from normalise.text import IDENTITY_WORDS, TYPE_WORDS, fold, split_number, street_key, strip_marks

# verbatim from the register
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


def test_fold() -> None:
    for raw, expected in [
        ("Αχαρνών", "ΑΧΑΡΝΩΝ"),
        ("Αγίου Ιωάννου", "ΑΓΙΟΥ ΙΩΑΝΝΟΥ"),
        ("Ελλησπόντου", "ΕΛΛΗΣΠΟΝΤΟΥ"),
        ("ΑΧΑΡΝΩΝ", "ΑΧΑΡΝΩΝ"),
    ]:
        assert fold(raw) == expected
    assert fold("Οδός") == fold("ΟΔΟΣ") == "ΟΔΟΣ"
    assert fold("Αϊβαλίου") == "ΑΙΒΑΛΙΟΥ"
    assert fold("  ΑΓΙΟΥ   ΙΩΑΝΝΟΥ \n") == "ΑΓΙΟΥ ΙΩΑΝΝΟΥ"
    assert fold("Α’ ΠΑΡΟΔΟΣ") == fold("Α' ΠΑΡΟΔΟΣ") == "Α' ΠΑΡΟΔΟΣ"


def test_street_key() -> None:
    for raw, expected in [
        ("ΟΔΟΣ ΑΧΑΡΝΩΝ", "ΑΧΑΡΝΩΝ"),
        ("ΛΕΩΦΟΡΟΣ ΙΩΑΝΝΗ ΚΑΠΟΔΙΣΤΡΙΟΥ", "ΙΩΑΝΝΗ ΚΑΠΟΔΙΣΤΡΙΟΥ"),
        ("ΛΕΩΦ. ΑΛΕΞΑΝΔΡΑΣ", "ΑΛΕΞΑΝΔΡΑΣ"),
        ("Λεωφόρου Κηφισίας", "ΚΗΦΙΣΙΑΣ"),
    ]:
        assert street_key(raw) == expected

    # ΠΑΡΟΔΟΣ ends in ΟΔΟΣ
    for raw in [
        "ΠΑΡΟΔΟΣ ΑΧΑΡΝΩΝ",
        "Α' ΠΑΡΟΔΟΣ ΔΗΜΟΣΘΕΝΟΥΣ",
        "ΠΛΑΤΕΙΑ ΜΑΚΑΡΙΟΥ",
        "ΠΑΡΟΔΟΥ ΑΓΙΟΥ ΔΗΜΗΤΡΙΟΥ",
        "Α' ΑΔΙΕΞΟΔΟΣ ΜΑΡΑΣΛΗ",
        "2Η ΠΑΡΟΔΟΣ ΣΚΡΑ",
    ]:
        assert street_key(raw) == fold(raw)
    assert street_key("ΠΑΡΟΔΟΣ ΑΧΑΡΝΩΝ") != street_key("ΟΔΟΣ ΑΧΑΡΝΩΝ")
    assert street_key("2Η ΠΑΡΟΔΟΣ ΣΚΡΑ") != street_key("3Η ΠΑΡΟΔΟΣ ΣΚΡΑ")
    assert street_key("Α' ΠΑΡΟΔΟΣ ΔΗΜΟΣΘΕΝΟΥΣ") != street_key("Γ' ΠΑΡΟΔΟΣ ΔΗΜΟΣΘΕΝΟΥΣ")
    assert street_key("ΟΔΟΣ") == "ΟΔΟΣ"
    assert not (TYPE_WORDS & IDENTITY_WORDS)

    for sample in REGISTER_SAMPLES:
        key = street_key(sample)
        assert key == street_key(key)
        assert key.strip() == key


@given(st.text())
def test_fold_idempotent(text: str) -> None:
    assert fold(fold(text)) == fold(text)


@given(st.text())
def test_street_key_idempotent(text: str) -> None:
    assert street_key(street_key(text)) == street_key(text)


@given(st.text(min_size=1).filter(lambda s: s.strip()))
def test_street_key_never_empty(text: str) -> None:
    assert street_key(text) != ""


@given(st.text())
def test_fold_marks(text: str) -> None:
    # a name of only combining marks keeps them, "" would match every row
    if not strip_marks(text).strip():
        return
    assert not any(unicodedata.combining(c) for c in fold(text))


def test_split_number() -> None:
    assert split_number("ΑΛΕΞΑΝΔΡΟΥ ΣΥΜΕΩΝΙΔΗ 8") == ("ΑΛΕΞΑΝΔΡΟΥ ΣΥΜΕΩΝΙΔΗ", "8")
    assert split_number("ΑΘΗΝΑΣ 12Α") == ("ΑΘΗΝΑΣ", "12Α")
    assert split_number("ΑΛΕΞΑΝΔΡΟΥ ΣΥΜΕΩΝΙΔΗ") == ("ΑΛΕΞΑΝΔΡΟΥ ΣΥΜΕΩΝΙΔΗ", None)
    # there are streets called 8
    assert split_number("8") == ("8", None)
    assert split_number("25ΗΣ ΜΑΡΤΙΟΥ 52") == ("25ΗΣ ΜΑΡΤΙΟΥ", "52")
