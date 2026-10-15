from __future__ import annotations

import re
import unicodedata

# uppercase Greek has no accents (ΑΧΑΡΝΩΝ), and upper() already merges ς and σ

# Α' ΠΑΡΟΔΟΣ, with whatever apostrophe the filer had
APOSTROPHES = "\u2019\u2018\u00b4\u0384\u02bc"

# say what kind of street, not which one
TYPE_WORDS = frozenset({"ΟΔΟΣ", "ΟΔΟΥ", "ΛΕΩΦΟΡΟΣ", "ΛΕΩΦΟΡΟΥ", "ΛΕΩΦ"})

# end in ΟΔΟΣ but are places of their own, must survive folding (tests only)
IDENTITY_WORDS = frozenset({"ΠΑΡΟΔΟΣ", "ΠΑΡΟΔΟΥ", "ΠΛΑΤΕΙΑ", "ΑΔΙΕΞΟΔΟΣ", "ΑΔΙΕΞΟΔΟΥ"})


def strip_marks(text: str) -> str:
    # tonos and dialytika
    return "".join(c for c in unicodedata.normalize("NFD", text) if not unicodedata.combining(c))


def fold(text: str) -> str:
    """Accent-free, uppercase, single-spaced."""
    s = strip_marks(text).upper()
    for c in APOSTROPHES:
        s = s.replace(c, "'")
    s = " ".join(s.split())
    # a name of nothing but combining marks would fold to ""
    return s if s else " ".join(text.upper().split())


def street_key(name: str) -> str:
    kept = [t for t in fold(name).split(" ") if t.rstrip(".") not in TYPE_WORDS]
    # an empty key would match everything
    return " ".join(kept) if kept else fold(name)


HOUSE_NUMBER = re.compile(r"^\d+[Α-ΩA-Z]?$")  # 12, 12Α


def split_number(folded: str) -> tuple[str, str | None]:
    """Split the house number off the end of a folded query."""
    t = folded.split(" ")
    if len(t) > 1 and HOUSE_NUMBER.fullmatch(t[-1]):
        return " ".join(t[:-1]), t[-1]
    return folded, None
