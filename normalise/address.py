"""Parse the register's packed address field."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from normalise.greeklish import from_greek
from normalise.text import fold, street_key

# 'postcode,STREET,NUMBER,MUNICIPALITY', several per point on 6.43% of points: a corner
# building is filed under both its streets.
ADDRESS_SEPARATOR = "|"
FIELD_SEPARATOR = ","
FIELDS = 4

# The last field is the locality, and 93.6% carry the municipality prefix 'Δ. '.
LOCALITY_PREFIX = "Δ."

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
    """Blank and whitespace-only fields are absent, never empty strings."""
    stripped = field.strip()
    return stripped if stripped else None


def postcode_of(field: str) -> str | None:
    """A postcode only if well formed. A malformed one is unknown, never repaired."""
    value = clean(field)
    if value is None:
        return None
    return value if len(value) == POSTCODE_DIGITS and value.isdigit() else None


def locality_of(field: str) -> str | None:
    value = clean(field)
    if value is None:
        return None
    if value.startswith(LOCALITY_PREFIX):
        value = value[len(LOCALITY_PREFIX) :].strip()
    return clean(value)


@lru_cache(maxsize=1 << 17)
def keyed(street: str, locality: str | None) -> tuple[str, str, str]:
    """street_fold, search_key and latin_key for a street in a locality.

    Cached. Each is a Unicode normalisation plus a transliteration, and the pairs repeat
    constantly: a 400,000-point sample had about 26,000 distinct ones. Pure, so caching only
    changes the time taken.
    """
    folded = street_key(street)
    key = folded
    if locality is not None:
        key = f"{key} {fold(locality)}"
    return folded, key, from_greek(key)


def parse_part(part: str) -> ParsedAddress | None:
    """One address, or None when the field doesn't have the shape we know."""
    fields = part.split(FIELD_SEPARATOR)
    if len(fields) != FIELDS:
        return None

    street = clean(fields[1])
    if street is None:
        return None

    locality = locality_of(fields[3])
    folded, key, latin = keyed(street, locality)

    return ParsedAddress(
        postcode=postcode_of(fields[0]),
        street=street,
        street_fold=folded,
        street_no=clean(fields[2]),
        locality=locality,
        search_key=key,
        latin_key=latin,
    )


def parse(raw: str) -> list[ParsedAddress]:
    """Every address a point is filed under, in register order."""
    parsed = (parse_part(p) for p in raw.split(ADDRESS_SEPARATOR))
    return [p for p in parsed if p is not None]
