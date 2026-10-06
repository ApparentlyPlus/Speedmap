"""Fold Greek street names for search and comparison."""

from __future__ import annotations

import re
import unicodedata

# Greek uppercase drops accents, so folding has to as well: ΑΧΑΡΝΩΝ, never ΑΧΑΡΝΏΝ.
# str.upper() already handles final sigma, so ς and σ fold together on their own.

# ordinals are written Α' ΠΑΡΟΔΟΣ, with whatever apostrophe the filer had to hand
APOSTROPHES = "\u2019\u2018\u00b4\u0384\u02bc"

# type words say what kind of street it is and not which one, so search ignores them
TYPE_WORDS = frozenset({"ΟΔΟΣ", "ΟΔΟΥ", "ΛΕΩΦΟΡΟΣ", "ΛΕΩΦΟΡΟΥ", "ΛΕΩΦ"})

# Names that must survive folding. Only the tests use this. ΠΑΡΟΔΟΣ and ΑΔΙΕΞΟΔΟΣ both
# end in ΟΔΟΣ and both name places of their own.
IDENTITY_WORDS = frozenset({"ΠΑΡΟΔΟΣ", "ΠΑΡΟΔΟΥ", "ΠΛΑΤΕΙΑ", "ΑΔΙΕΞΟΔΟΣ", "ΑΔΙΕΞΟΔΟΥ"})


def strip_marks(text: str) -> str:
    """Drop combining marks, so tonos and dialytika stop separating otherwise equal names."""
    return "".join(c for c in unicodedata.normalize("NFD", text) if not unicodedata.combining(c))


def fold(text: str) -> str:
    """Accent-free, uppercase, single-spaced. The generic key for any register text.

    A name made only of combining marks folds to nothing, so it's kept uppercased instead.
    """
    folded = strip_marks(text).upper()
    for mark in APOSTROPHES:
        folded = folded.replace(mark, "'")
    collapsed = " ".join(folded.split())
    return collapsed if collapsed else " ".join(text.upper().split())


def street_key(name: str) -> str:
    """fold(), with type words dropped as whole tokens."""
    kept = [t for t in fold(name).split(" ") if t.rstrip(".") not in TYPE_WORDS]
    # all type words? keep them, since an empty key matches everything
    return " ".join(kept) if kept else fold(name)


# a house number as the register writes it: digits, sometimes a letter (12Α, 8Β)
HOUSE_NUMBER = re.compile(r"^\d+[Α-ΩA-Z]?$")


def split_number(folded: str) -> tuple[str, str | None]:
    """Split a folded query into the street and the house number it ends with.

    The index holds street and locality, never the number.
    """
    tokens = folded.split(" ")
    if len(tokens) > 1 and HOUSE_NUMBER.fullmatch(tokens[-1]):
        return " ".join(tokens[:-1]), tokens[-1]
    return folded, None
