"""How the operators spell an address, which is not how Καλλικράτης does.

Both of the operators that want an address in words want the same words: prefectures and
pre-Καλλικράτης municipalities, which is why only 164 of their 506 share a name with one of
our 333. One asks for Ν. ΑΤΤΙΚΗΣ and Δ. ΑΘΗΝΑΙΩΝ, the other for ΑΤΤΙΚΗΣ and ΑΘΗΝΑΙΩΝ, and
the difference between them is a prefix rather than a vocabulary.

The scrape recorded that vocabulary for every street it walked, so it is read back here
rather than rebuilt by walking six dropdown calls per address.
"""

from __future__ import annotations

from dataclasses import dataclass

import psycopg
from psycopg.rows import TupleRow

NAMING = """
select nomos, dimos, area, street, street_type
from raw_cosmote
where municipality_id = %s and street_fold = %s
limit 1
"""


@dataclass(frozen=True)
class Naming:
    """One address, spelled the way the operators spell it."""

    nomos: str
    dimos: str
    area: str | None
    street: str
    street_type: str | None


def naming(
    conn: psycopg.Connection[TupleRow], municipality_id: int, street_fold: str
) -> Naming | None:
    """Their spelling of this street, if the scrape ever walked it."""
    row = conn.execute(NAMING, (municipality_id, street_fold)).fetchone()
    if row is None:
        return None
    return Naming(
        nomos=str(row[0]),
        dimos=str(row[1]),
        area=None if row[2] is None else str(row[2]),
        street=str(row[3]),
        street_type=None if row[4] is None else str(row[4]),
    )
