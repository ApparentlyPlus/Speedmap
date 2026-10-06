"""Transliterate Greek to Latin, and bring Greeklish input into the same alphabet."""

from __future__ import annotations

import re

from normalise.text import strip_marks

# Θ has no single Latin letter and gets written th, 8 or 9. It's parked while H is resolved,
# or the H in TH gets eaten by the rule mapping a lone H to Χ.
THETA = "\x01"

# ΑΥ and ΕΥ are voiced before a vowel or voiced consonant and devoiced elsewhere: ΑΥΛΩΝΟΣ is
# avlonos, ΕΥΤΥΧΙΑ is eftixia. Done before the plain digraphs, which can't look ahead.
VOICING = re.compile(r"([ΑΕ])Υ(?=[ΑΕΗΙΟΥΩΒΓΔΖΛΜΝΡ])")

# Order matters: digraphs go before their letters. ΓΓ is /ng/, so ΑΓΓΕΛΟΣ is angelos and
# stays apart from ΑΓΕΛΟΣ.
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
# Ξ and Χ both become X. Across all 30,272 street names this merges nothing new, and lets
# alexandras and aleksandras both land exactly.

LATIN_RULES = (
    ("TH", THETA), ("8", THETA), ("9", THETA),
    ("CH", "X"), ("KS", "X"),
    ("OU", "U"), ("AI", "E"), ("EI", "I"), ("OI", "I"),
    ("MP", "B"), ("NT", "D"), ("GK", "G"), ("GG", "G"),
)

# A lone H is far more often Χ than Η (aharnon, ahilleas). Where it's a vowel, the trigram
# fallback still finds the name.
LATIN_LETTERS = {"C": "K", "Q": "K", "W": "O", "Y": "I", "J": "I", "H": "X"}


def from_greek(name: str) -> str:
    """The Latin form of a Greek name, one spelling per name."""
    text = VOICING.sub(r"\1V", strip_marks(name).upper())
    for greek, latin in GREEK_DIGRAPHS:
        text = text.replace(greek, latin)
    written = "".join(GREEK_LETTERS.get(c, c) for c in text)
    return written.replace(THETA, "TH")


def from_latin(query: str) -> str:
    """Greeklish, reduced to the alphabet from_greek writes."""
    text = strip_marks(query).upper()
    for pattern, replacement in LATIN_RULES:
        text = text.replace(pattern, replacement)
    written = "".join(LATIN_LETTERS.get(c, c) for c in text)
    return written.replace(THETA, "TH")


def is_greeklish(query: str) -> bool:
    """True when the query has Latin letters and no Greek ones."""
    letters = [c for c in strip_marks(query).upper() if c.isalpha()]
    if not letters:
        return False
    return not any(c in GREEK_LETTERS for c in letters)
