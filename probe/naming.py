"""How the operators spell an address, which is not how Καλλικράτης does.

Both of the operators that want an address in words want the same words: prefectures and
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

# The spellings in use closest to this address. Ordered by distance off the gist index, which is
# what `<->` reads: 24ms against 1.3M rows, on a path that already spends seconds on the network.
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

# What the scrape calls a street, in the one case out of 64,871 that is not ΟΔΟΣ.
STREET_TYPE = "ΟΔΟΣ"

# How far away a walked address may be and still be trusted for the spelling of this one.
NEARBY_M = 500.0

# How many walked addresses to look at before deduplicating them into spellings. Enough to
# cross a district boundary and offer both sides, small enough to stay an index scan.
LOOK = 40

# How many spellings an adapter that can verify will try before giving up.
TRIES = 4


@dataclass(frozen=True)
class Naming:
    """One address, spelled the way the operators spell it."""

    nomos: str
    dimos: str
    area: str | None
    street: str
    street_type: str | None
    # True when the scrape actually walked this street.
    exact: bool = True
    # How far away that neighbour was, in metres. None on an exact naming, which is about
    # this street rather than about the one next to it.
    metres: float | None = None


def naming(
    conn: psycopg.Connection[TupleRow], municipality_id: int, street_fold: str
) -> Naming | None:
    """Their spelling of this street, if the scrape ever walked it."""
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
    """Every spelling worth trying for this address, nearest first.

    One entry when the scrape walked the street.
    """
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
