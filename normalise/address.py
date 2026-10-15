"""Parse the register's packed address field."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from normalise.greeklish import from_greek
from normalise.text import fold, street_key

# 'postcode,STREET,NUMBER,MUNICIPALITY', and 6.43% of points have several (corner buildings)
ADDRESS_SEPARATOR = "|"
FIELD_SEPARATOR = ","
FIELDS = 4

LOCALITY_PREFIX = "Δ."  # on 93.6% of localities

POSTCODE_DIGITS = 5


@dataclass(frozen=True)
class ParsedAddress:
    postcode: str | None
    street: str
    street_fold: str
    street_no: str | None
    locality: str | None
    search_key: str
    latin_key: str


def clean(field: str) -> str | None:
    s = field.strip()
    return s if s else None


# ~26k distinct pairs in a 400k point sample
@lru_cache(maxsize=1 << 17)
def keyed(street: str, locality: str | None) -> tuple[str, str, str]:
    """street_fold, search_key and latin_key."""
    folded = street_key(street)
    key = folded
    if locality is not None:
        key = f"{key} {fold(locality)}"
    return folded, key, from_greek(key)


def parse_part(part: str) -> ParsedAddress | None:
    fields = part.split(FIELD_SEPARATOR)
    if len(fields) != FIELDS:
        return None

    street = clean(fields[1])
    if street is None:
        return None

    # a malformed postcode is unknown, never repaired
    postcode = clean(fields[0])
    if postcode is not None and not (len(postcode) == POSTCODE_DIGITS and postcode.isdigit()):
        postcode = None

    locality = clean(fields[3])
    if locality is not None and locality.startswith(LOCALITY_PREFIX):
        locality = clean(locality[len(LOCALITY_PREFIX) :])

    folded, key, latin = keyed(street, locality)
    return ParsedAddress(
        postcode=postcode,
        street=street,
        street_fold=folded,
        street_no=clean(fields[2]),
        locality=locality,
        search_key=key,
        latin_key=latin,
    )


def parse(raw: str) -> list[ParsedAddress]:
    parsed = (parse_part(p) for p in raw.split(ADDRESS_SEPARATOR))
    return [p for p in parsed if p is not None]
