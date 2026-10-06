"""How the operators spell an address, which isn't how Καλλικράτης does.

Both operators that want an address in words want the same ones: prefectures and
pre-Καλλικράτης municipalities.
"""

from __future__ import annotations

from dataclasses import dataclass

import psycopg
from psycopg.rows import TupleRow

EXACT = """
select nomos, dimos, area, street, street_type
from raw_cosmote
where municipality_id = %s and street_fold = %s
limit 1
"""

# The spellings nearest this address, ordered by distance off the gist index (what `<->`
# reads): 24 ms over 1.3M rows, on a path already spending seconds on the network.
NEAREST = """
select distinct on (nomos, dimos, area)
       nomos, dimos, area, st_distance(geom, %(here)s) as metres
from (
    select nomos, dimos, area, geom
    from raw_cosmote
    where municipality_id = %(municipality)s
    order by geom <-> %(here)s
    limit %(look)s
) near
order by nomos, dimos, area, metres
"""

# the scrape's street type, which is ΟΔΟΣ in all but one of 64,871 cases
STREET_TYPE = "ΟΔΟΣ"

# how far a walked address can be and still lend its spelling to this one
NEARBY_M = 500.0

# Walked addresses to look at before deduplicating into spellings. Enough to cross a
# district boundary and offer both sides, few enough to stay an index scan.
LOOK = 40

# spellings a verifying adapter tries before giving up
TRIES = 4


@dataclass(frozen=True)
class Naming:
    """One address, spelled the operators' way."""

    nomos: str
    dimos: str
    area: str | None
    street: str
    street_type: str | None
    # True when the scrape walked this very street
    exact: bool = True
    # Metres to the neighbour it came from. None on an exact naming, which is about this
    # street itself.
    metres: float | None = None


def naming(
    conn: psycopg.Connection[TupleRow], municipality_id: int, street_fold: str
) -> Naming | None:
    """Their spelling of this street, if the scrape walked it."""
    row = conn.execute(EXACT, (municipality_id, street_fold)).fetchone()
    if row is None:
        return None
    return Naming(
        nomos=str(row[0]),
        dimos=str(row[1]),
        area=None if row[2] is None else str(row[2]),
        street=str(row[3]),
        street_type=None if row[4] is None else str(row[4]),
    )


def namings(
    conn: psycopg.Connection[TupleRow],
    municipality_id: int,
    street_fold: str,
    lat: float | None = None,
    lon: float | None = None,
) -> list[Naming]:
    """Every spelling worth trying here, nearest first. Just one if the scrape walked it."""
    exact = naming(conn, municipality_id, street_fold)
    if exact is not None:
        return [exact]
    if lat is None or lon is None:
        return []
    found = conn.execute(NEAREST, {
        "municipality": municipality_id,
        "here": f"SRID=4326;POINT({lon} {lat})",
        "look": LOOK,
    }).fetchall()
    return sorted(
        (
            Naming(
                nomos=str(nomos), dimos=str(dimos), area=str(area),
                street=street_fold, street_type=STREET_TYPE,
                exact=False, metres=float(metres),
            )
            for nomos, dimos, area, metres in found
            if float(metres) <= NEARBY_M
        ),
        key=lambda n: n.metres if n.metres is not None else 0.0,
    )[:TRIES]
