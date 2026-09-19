"""How the operators spell an address, which is not how Καλλικράτης does.

Both of the operators that want an address in words want the same words: prefectures and
pre-Καλλικράτης municipalities, which is why only 164 of their 506 share a name with one of
our 333. One asks for Ν. ΑΤΤΙΚΗΣ and Δ. ΑΘΗΝΑΙΩΝ, the other for ΑΤΤΙΚΗΣ and ΑΘΗΝΑΙΩΝ, and
the difference between them is a prefix rather than a vocabulary.

The scrape recorded that vocabulary for every street it walked, so it is read back here
rather than rebuilt by walking six dropdown calls per address.

It walked 43% of streets. For the rest the municipality is very often still known — 246 of
our 333 appear somewhere in the scrape — and that turns out to be nearly enough, because
the street-level half of the lookup is mostly not a lookup at all:

  * street_type is ΟΔΟΣ for 64,870 of the 64,871 streets in the scrape. It is a constant
    wearing the shape of a field.
  * area is already optional; the caller falls back to the municipality when it is absent.
  * their spelling of a street IS our fold. raw_cosmote.street equals street_fold in 96% of
    rows, and against our own display names the only differences are case and accent, which
    they ignore. The 4% is a leading type word the fold strips — ΛΕΩΦΟΡΟΣ ΑΛΕΞΑΝΔΡΑΣ
    against ΑΛΕΞΑΝΔΡΑΣ — and is the known cost of guessing.

So what is left to guess is the municipality, and the two adapters are not equally able to
guess it. Nova asks their street list and matches, so a wrong municipality returns nothing
and the next one can be tried. Cosmote posts a form and takes what comes back, so a wrong
municipality answers about a different street — which is worse than not answering.

Only Nova guesses, and this was settled by asking rather than by reasoning. Cosmote was
given the right prefecture, the right municipality and a real exchange area borrowed from a
walked address fifteen metres off, and its form still answered "διερεύνηση" on every guessed
address and on none of the walked ones — because the scrape IS their address book. It was
made by walking their dropdowns, so a street missing from it for a municipality is a street
they do not have under that name: Πατησίων is 28ης Οκτωβρίου to them, and their Δεριγνύ is
in Περιστέρι and Άνω Λιόσια and not in Αθηναίων. Nova has a street list to search, finds the
street under our name, and answers.

A guess is taken from the NEAREST address the scrape did walk rather than from the
commonest spelling in the municipality. The scrape's geocoding puts a few hundred Athens
addresses in Ηγουμενίτσα and Κιλκίς, and a frequency ranking has to argue them away with a
threshold; proximity never proposes them at all. The nearest walked address is a median of
87 metres away, 94% are within 250 and all of them within 500.
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

# The spellings in use closest to this address. Ordered by distance off the gist index,
# which is what `<->` reads: 24ms against 1.3M rows, on a path that already spends seconds
# on the network.
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
# Every unwalked address sampled had one within 500 m and the median was 87, so this is a
# bound rather than a filter — an exchange district is kilometres across, and a neighbour
# two streets over is in the same one.
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
    # True when the scrape actually walked this street. False when the spelling was borrowed
    # from the nearest address it did walk, and the street name is our own fold — good
    # enough to ask with, and good enough to believe only when the neighbour is close.
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

    One entry when the scrape walked the street. Otherwise one per prefecture, municipality
    and area in use around it, each carrying our fold as the street name — which is what
    they call it too, 96% of the time.
    """
    walked = naming(conn, municipality_id, street_fold)
    if walked is not None:
        return [walked]
    if lat is None or lon is None:
        return []
    rows = conn.execute(NEAREST, {
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
            for nomos, dimos, area, metres in rows
            if float(metres) <= NEARBY_M
        ),
        key=lambda n: n.metres if n.metres is not None else 0.0,
    )[:TRIES]
