"""Fold Greek street names for search and comparison."""

from __future__ import annotations

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
    """Accent-free, uppercase, single-spaced. The generic key used for any register text."""
    folded = strip_marks(text).upper()
    for mark in APOSTROPHES:
        folded = folded.replace(mark, "'")
    return " ".join(folded.split())


def street_key(name: str) -> str:
    """fold(), with type words dropped as whole tokens."""
    kept = [t for t in fold(name).split(" ") if t.rstrip(".") not in TYPE_WORDS]
    # A name that is nothing but type words keeps them: an empty key matches everything.
    return " ".join(kept) if kept else fold(name)
