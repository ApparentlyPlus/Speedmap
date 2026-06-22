"""Fold Greek street names for search and comparison."""

from __future__ import annotations

import re
import unicodedata

# Greek uppercase legitimately drops accents, so folding must match: ΑΧΑΡΝΩΝ, not ΑΧΑΡΝΏΝ.
# str.upper() already maps final sigma, so ς and σ fold together without help.

# Ordinals are written Α' ΠΑΡΟΔΟΣ, and the register mixes apostrophe characters freely.
APOSTROPHES = "\u2019\u2018\u00b4\u0384\u02bc"

# Type words: they say what kind of thing this is, not which one, so search ignores them.
TYPE_WORDS = frozenset({"ΟΔΟΣ", "ΟΔΟΥ", "ΛΕΩΦΟΡΟΣ", "ΛΕΩΦΟΡΟΥ", "ΛΕΩΦ"})

# Names that must survive folding intact. Asserted in the tests, not used by the code.
# ΠΑΡΟΔΟΣ and ΑΔΙΕΞΟΔΟΣ both end in ΟΔΟΣ and both name a place of their own.
IDENTITY_WORDS = frozenset({"ΠΑΡΟΔΟΣ", "ΠΑΡΟΔΟΥ", "ΠΛΑΤΕΙΑ", "ΑΔΙΕΞΟΔΟΣ", "ΑΔΙΕΞΟΔΟΥ"})


def strip_marks(text: str) -> str:
    """Drop combining marks, so tonos and dialytika stop distinguishing otherwise equal names."""
    return "".join(c for c in unicodedata.normalize("NFD", text) if not unicodedata.combining(c))


def fold(text: str) -> str:
    """Accent-free, uppercase, single-spaced. The generic key used for any register text.

    A name made only of combining marks folds away to nothing, because that is all stripping
    marks can do with it. It keeps its own characters instead: an empty key is not a folded
    name, it is a key that matches every row in the table.
    """
    folded = strip_marks(text).upper()
    for mark in APOSTROPHES:
        folded = folded.replace(mark, "'")
    collapsed = " ".join(folded.split())
    return collapsed if collapsed else " ".join(text.upper().split())


def street_key(name: str) -> str:
    """fold(), with type words dropped as whole tokens."""
    kept = [t for t in fold(name).split(" ") if t.rstrip(".") not in TYPE_WORDS]
    # A name that is nothing but type words keeps them: an empty key matches everything.
    return " ".join(kept) if kept else fold(name)


# A house number as the register writes them: digits, sometimes a letter after (12Α, 8Β).
# A range or a fraction is kept verbatim by the register and is not recognised here, so a
# query carrying one falls back to searching the street, which is what it did before.
HOUSE_NUMBER = re.compile(r"^\d+[Α-ΩA-Z]?$")


def split_number(folded: str) -> tuple[str, str | None]:
    """A folded query split into the street part and the house number it ends with.

    The search index holds the street and the locality and never the number, so a number
    left in the query matches nothing and still outvotes the part that does: searching
    "ΣΥΜΕΩΝΙΔΗ 8" scored worse against Συμεωνίδη than "ΣΥΜΕΩΝΙΔΗ" alone did, and returned
    numbers 58, 60, 13 and 10. Taken out, it can do the job it was typed for, which is to
    pick one address out of the street.

    Only a trailing token counts, and only when something is left over: "8" on its own is a
    search for a street named 8, and Greece has a few.
    """
    tokens = folded.split(" ")
    if len(tokens) > 1 and HOUSE_NUMBER.fullmatch(tokens[-1]):
        return " ".join(tokens[:-1]), tokens[-1]
    return folded, None
