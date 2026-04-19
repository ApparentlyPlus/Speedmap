"""Parse the register's packed address field."""

from __future__ import annotations

from dataclasses import dataclass

from normalise.text import fold, street_key

# 'postcode,STREET,NUMBER,MUNICIPALITY', and one point may carry several of them.
# 6.43% of points do: a corner building is filed under both of its streets.
ADDRESS_SEPARATOR = "|"
FIELD_SEPARATOR = ","
FIELDS = 4

# The field is the locality, but 93.6% carry the municipality prefix 'Δ. '. Same type word as ΟΔΟΣ.
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


def clean(field: str) -> str | None:
    """Blank and whitespace-only fields are absent, not empty strings."""
    stripped = field.strip()
    return stripped if stripped else None


def postcode_of(field: str) -> str | None:
    """Only a well-formed postcode is a postcode; a malformed one is unknown, never repaired."""
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


def parse_part(part: str) -> ParsedAddress | None:
    """One address, or None when the field does not have the shape we know."""
    fields = part.split(FIELD_SEPARATOR)
    if len(fields) != FIELDS:
        return None

    street = clean(fields[1])
    if street is None:
        return None

    locality = locality_of(fields[3])
    folded = street_key(street)
    key = folded
    if locality is not None:
        key = f"{key} {fold(locality)}"

    return ParsedAddress(
        postcode=postcode_of(fields[0]),
        street=street,
        street_fold=folded,
        street_no=clean(fields[2]),
        locality=locality,
        search_key=key,
    )


def parse(raw: str) -> list[ParsedAddress]:
    """Every address the point is filed under, in the order the register lists them."""
    parsed = (parse_part(p) for p in raw.split(ADDRESS_SEPARATOR))
    return [p for p in parsed if p is not None]
