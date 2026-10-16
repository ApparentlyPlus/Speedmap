"""Transliterate Greek to Latin, and bring Greeklish input into the same alphabet."""

from __future__ import annotations

import re

from normalise.text import strip_marks

# th, 8 or 9. Parked so the lone H rule below doesn't eat the H in TH
THETA = "\x01"

# ΑΥΛΩΝΟΣ is avlonos but ΕΥΤΥΧΙΑ is eftixia
VOICING = re.compile(r"([ΑΕ])Υ(?=[ΑΕΗΙΟΥΩΒΓΔΖΛΜΝΡ])")

# before the single letters. ΓΓ is ng so ΑΓΓΕΛΟΣ and ΑΓΕΛΟΣ stay apart
GREEK_DIGRAPHS = (
    ("ΟΥ", "U"), ("ΑΥ", "AF"), ("ΕΥ", "EF"),
    ("ΜΠ", "B"), ("ΝΤ", "D"), ("ΓΓ", "NG"), ("ΓΚ", "G"),
    ("ΤΣ", "TS"), ("ΤΖ", "TZ"),
    ("ΑΙ", "E"), ("ΕΙ", "I"), ("ΟΙ", "I"), ("ΥΙ", "I"),
)

GREEK_LETTERS = {
    "Α": "A", "Β": "V", "Γ": "G", "Δ": "D", "Ε": "E", "Ζ": "Z", "Η": "I",
    "Θ": THETA, "Ι": "I", "Κ": "K", "Λ": "L", "Μ": "M", "Ν": "N", "Ξ": "X",
    "Ο": "O", "Π": "P", "Ρ": "R", "Σ": "S", "Τ": "T", "Υ": "I", "Φ": "F",
    "Χ": "X", "Ψ": "PS", "Ω": "O",
}
# Ξ and Χ both go to X, merges nothing across all 30,272 streets

LATIN_RULES = (
    ("TH", THETA),
    ("CH", "X"), ("KS", "X"),
    ("OU", "U"), ("AI", "E"), ("EI", "I"), ("OI", "I"),
    # GG is NG like ΓΓ, aggelou is ΑΓΓΕΛΟΥ
    ("MP", "B"), ("NT", "D"), ("GK", "G"), ("GG", "NG"),
)

# θ inside a word only, ermou 18 keeps its 8
NUMBER = re.compile(r"\d+[A-Z]?")

# a lone H is usually Χ (aharnon, ahilleas), trigrams catch the rest
LATIN_LETTERS = {"C": "K", "Q": "K", "W": "O", "Y": "I", "J": "I", "H": "X"}


def from_greek(name: str) -> str:
    s = VOICING.sub(r"\1V", strip_marks(name).upper())
    for a, b in GREEK_DIGRAPHS:
        s = s.replace(a, b)
    return "".join(GREEK_LETTERS.get(c, c) for c in s).replace(THETA, "TH")


def from_latin(query: str) -> str:
    """Greeklish, reduced to the alphabet from_greek writes."""
    s = " ".join(
        w if NUMBER.fullmatch(w) else w.replace("8", THETA).replace("9", THETA)
        for w in strip_marks(query).upper().split(" ")
    )
    for a, b in LATIN_RULES:
        s = s.replace(a, b)
    return "".join(LATIN_LETTERS.get(c, c) for c in s).replace(THETA, "TH")


def is_greeklish(query: str) -> bool:
    letters = [c for c in strip_marks(query).upper() if c.isalpha()]
    if not letters:
        return False
    return not any(c in GREEK_LETTERS for c in letters)
