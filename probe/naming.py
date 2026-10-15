"""The operators' spelling of an address: prefectures and pre-Καλλικράτης municipalities."""

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

# knn on the gist index, 24 ms over 1.3M rows
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

STREET_TYPE = "ΟΔΟΣ"  # all but one of 64,871

NEARBY_M = 500.0

# enough to cross a district boundary, few enough for an index scan
LOOK = 40

TRIES = 4


@dataclass(frozen=True)
class Naming:
    nomos: str
    dimos: str
    area: str | None
    street: str
    street_type: str | None
    exact: bool = True  # the scrape walked this very street
    metres: float | None = None  # to the neighbour it was borrowed from


def naming(conn: psycopg.Connection[TupleRow], municipality_id: int, street_fold: str) -> Naming | None:
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


def namings(conn: psycopg.Connection[TupleRow], municipality_id: int, street_fold: str,
            lat: float | None = None, lon: float | None = None) -> list[Naming]:
    """Spellings worth trying, nearest first, or the exact one alone."""
    exact = naming(conn, municipality_id, street_fold)
    if exact is not None:
        return [exact]
    if lat is None or lon is None:
        return []

    rows = conn.execute(NEAREST, {"municipality": municipality_id, "here": f"SRID=4326;POINT({lon} {lat})",
                                  "look": LOOK}).fetchall()
    near = [
        Naming(nomos=str(nomos), dimos=str(dimos), area=str(area), street=street_fold, street_type=STREET_TYPE,
               exact=False, metres=float(m))
        for nomos, dimos, area, m in rows
        if float(m) <= NEARBY_M
    ]
    return sorted(near, key=lambda n: n.metres if n.metres is not None else 0.0)[:TRIES]
