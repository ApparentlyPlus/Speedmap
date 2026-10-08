"""JSON over the register. Computes nothing, returns stored state.

Read only, apart from three writes: reader reports, addresses made because a reader asked, and
what an operator said when one was asked.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated, Any, Literal

import psycopg
from fastapi import FastAPI, HTTPException, Query
from psycopg_pool import ConnectionPool
from pydantic import BaseModel, Field

from api.throttle import throttled
from db.settings import settings
from normalise.greeklish import from_latin, is_greeklish
from normalise.propose import propose
from normalise.text import fold, split_number, street_key
from probe.adapter import Adapter
from probe.cosmote import Cosmote
from probe.health import health as adapter_state
from probe.lookup import verdicts
from probe.nova import Nova
from probe.run import refresh, target_for
from probe.vodafone import Vodafone
from ranking.offer import options as buyable
from ranking.rank import ENOUGH_MBPS, rank

# JIT off. Every query here is an index lookup of a millisecond or two, and compiling one
# because a spatial estimate crossed jit_above_cost costs a hundred times that on a Pi. Four
# connections cap the load on the database.
pool = ConnectionPool(
    settings.dsn, min_size=1, max_size=4, open=False, kwargs={"options": "-c jit=off"},
)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    pool.open()
    try:
        yield
    finally:
        pool.close()


app = FastAPI(
    title="speedmap.gr",
    version="0.1.0",
    summary="Greek broadband coverage, from the national register",
    lifespan=lifespan,
)
app.middleware("http")(throttled)


class Health(BaseModel):
    ok: bool
    addresses: int = Field(description="rows in the address index")
    offers: int = Field(description="rows in address_coverage")


def rows(sql: str, params: tuple[object, ...] | dict[str, object] = ()) -> list[tuple[Any, ...]]:
    with pool.connection() as conn:
        return conn.execute(sql, params).fetchall()


# What a reader can report. Free text is capped, stored as typed, and only ever read as text.
KINDS = Literal["availability", "price", "address", "other"]

FILED = """
insert into report (kind, detail, address_id, provider_id, plan_id, contact)
values (%s, %s, %s, %s, %s, %s)
returning id, created_at
"""


class ReportIn(BaseModel):
    kind: KINDS
    detail: str = Field(min_length=10, max_length=2000, description="what looks wrong")
    address_id: int | None = Field(default=None, description="the address it is about")
    provider_id: int | None = None
    plan_id: int | None = None
    contact: str | None = Field(default=None, max_length=200, description="optional, to reply")


class Report(BaseModel):
    id: int
    created_at: datetime


@app.get("/health", response_model=Health, tags=["meta"])
def health() -> Health:
    """Whether the database answers, and whether it has been built."""
    row = rows("select (select count(*) from address), (select count(*) from address_coverage)")
    addresses, offers = row[0]
    return Health(ok=True, addresses=addresses, offers=offers)


MIN_QUERY = 2
MAX_RESULTS = 20

# The dot beside an address: the fastest of what an operator told us directly and what the
# best line into the building retails at, capped by its filing the way 110 caps a street.
# Uncapped, a door on a 2-10 Mbps cabinet showed 24 next to a street painted 10.
BEST_MBPS = """
    greatest(
        (select max(v.max_down_mbps) from availability v
         where v.address_id = a.id and v.serviceable),
        (select max(least(t.sold_mbps, coalesce(nb.max_mbps, sb.max_mbps)))
         from address_coverage ac
         join technology t on t.code = ac.technology
         left join speed_band sb on sb.id = ac.speed_band_id
         left join speed_band nb on nb.id = ac.normal_band_id
         where ac.address_id = a.id and ac.family <> 'wireless')
    )
"""

ADDRESS_COLUMNS = f"""
    'address', a.id, a.street, a.street_no, a.locality, m.name, a.postcode, a.premises,
    {BEST_MBPS}
"""

# A street's best speed and its locality are both stored by the build. Working them out per
# keystroke scanned every door of every street in the list. The locality is what separates
# two runs of one name in a municipality (7,320 names), and is null when a run has no doors.
STREET_COLUMNS = """
    'street', s.id, s.name, null, s.locality, m.name, null, null, s.best_mbps
"""

TIERS = ("prefix", "word", "fuzzy")  # three tiers, widening only while the page isn't full

STREET_SLOTS = 2  # streets shown first for a name typed without a number

# streets a bare number gets offered on (more than two is guessing)
PROPOSALS = 2


# the register files a lone dash for a missing street name, on 70 addresses
NAMELESS = "a.street <> '-'"


@dataclass(frozen=True)
class Term:
    """A query split into what to match and the house number to prefer."""

    folded: str
    number: str | None


# The typed house number sorts before everything else. It hangs on `nulls last`:
# `street_no = '107'` is true on that door, false on its neighbours and null on the 126,000
# rows with no number, and Postgres sorts nulls first under plain `desc`. Μητροπόλεως 107
# used to come back fourth, under three numberless doors.
NUMBER_FIRST = "(a.street_no = %s) desc nulls last, "


def condition(column: str, tier: str, tokens: list[str]) -> tuple[str, list[object]]:
    """The where clause and parameters for one tier.

    The word tier matches each token separately in any order, since Greek street names get
    filed both ways round.
    """
    joined = " ".join(tokens)
    prefix, anywhere = joined + "%", "% " + joined + "%"
    if tier == "prefix":
        return f"{column} like %s", [prefix]
    if tier == "word":
        # each token at the start of the key or of a word inside it
        each = " and ".join(f"({column} like %s or {column} like %s)" for _ in tokens)
        values: list[object] = []
        for token in tokens:
            values += [token + "%", "% " + token + "%"]
        return f"{each} and not ({column} like %s)", [*values, prefix]
    return (
        f"{column} %% %s and not ({column} like %s) and not ({column} like %s)",
        [joined, prefix, anywhere],
    )


def order(column: str, tier: str, tokens: list[str]) -> tuple[str, list[object]]:
    """Rows in a tier matched equally well, so only fuzzy ranks by similarity."""
    if tier != "fuzzy":
        return "", []
    return f"similarity({column}, %s) desc,", [" ".join(tokens)]


# Spellings a typo may have meant. Fuzzy matches against distinct spellings, then fetches
# the doors carrying the ones it liked.
KEY_SLOTS = 20


def fuzzy_address_sql(key: str, term: Term, limit: int) -> tuple[str, tuple[object, ...]]:
    """The fuzzy tier, run over distinct spellings instead of every door.

    Running `search_key % '…'` over all 1.8M addresses made it the slowest thing on the site
    by an order of magnitude.
    """
    tokens = term.folded.split(" ")
    joined = " ".join(tokens)
    prefix, anywhere = joined + "%", "% " + joined + "%"
    wanted, number = (NUMBER_FIRST, [term.number]) if term.number else ("", [])
    return (
        f"""
    select {ADDRESS_COLUMNS}
    from address a left join municipality m on m.id = a.municipality_id
    where {NAMELESS} and a.{key} in (
        select k.{key}
        from address_spelling k
        where k.{key} %% %s and not (k.{key} like %s) and not (k.{key} like %s)
        order by similarity(k.{key}, %s) desc, k.{key}
        limit {KEY_SLOTS}
    )
    order by {wanted}similarity(a.{key}, %s) desc, a.premises desc nulls last, a.id
    limit %s
    """,
        (joined, prefix, anywhere, joined, *number, joined, limit),
    )


def address_sql(key: str, tier: str, term: Term, limit: int) -> tuple[str, tuple[object, ...]]:
    if tier == "fuzzy":
        return fuzzy_address_sql(key, term, limit)
    column = "a." + key
    tokens = term.folded.split(" ")
    where, taken = condition(column, tier, tokens)
    ranked, ranking = order(column, tier, tokens)
    # the typed number sorts first, it's the most specific thing the reader gave us
    wanted, number = (NUMBER_FIRST, [term.number]) if term.number else ("", [])
    # The page of ids is picked first, from columns the prefix index carries, and only those
    # few rows get read in full, named and priced. Two letters match 77,000 doors, and each
    # used to be read and joined to its municipality to keep eight: 31,000 blocks per keystroke.
    return (
        f"""
    select {ADDRESS_COLUMNS}
    from (
        select a.id
        from address a
        where {NAMELESS} and {where}
        order by {wanted}{ranked} a.premises desc nulls last, a.id
        limit %s
    ) page
    join address a on a.id = page.id
    left join municipality m on m.id = a.municipality_id
    order by {wanted}{ranked} a.premises desc nulls last, a.id
    """,
        tuple(taken + number + ranking + [limit] + number + ranking),
    )


def street_sql(key: str, tier: str, term: Term, limit: int) -> tuple[str, tuple[object, ...]]:
    column = "s." + key
    tokens = term.folded.split(" ")
    where, taken = condition(column, tier, tokens)
    ranked, ranking = order(column, tier, tokens)
    return (
        f"""
    select {STREET_COLUMNS}
    from street s left join municipality m on m.id = s.municipality_id
    where {where}
    order by {ranked} s.ways desc, s.id
    limit %s
    """,
        tuple(taken + ranking + [limit]),
    )


class Result(BaseModel):
    kind: str = Field(description="address, street, or proposed")
    id: int
    name: str
    street_no: str | None
    locality: str | None = Field(
        description=(
            "for a door, as the register filed it. For a street, where most of its doors "
            "say they are, the one thing separating two runs of a name in one "
            "municipality. Null when it has no filed doors to ask"
        )
    )
    municipality: str | None
    postcode: str | None
    premises: int | None = Field(description="dwellings passed, null when not filed")
    best_mbps: Decimal | None = Field(
        description="the fastest known to reach here. Null is not filed, not zero"
    )
    match: str = Field(description="prefix, word, fuzzy or asked")
    street_id: int | None = Field(
        default=None,
        description="for a proposed address, the street to ask for it on",
    )


def proposable(key: str, tier: str, term: Term, limit: int) -> tuple[str, tuple[object, ...]]:
    """Streets a number could be on, looked up on their own.

    The tiers fill the page with addresses first and a street may never make it, so proposals
    can't be built from whatever the tiers returned.
    """
    column = "s." + key
    tokens = term.folded.split(" ")
    where, taken = condition(column, tier, tokens)
    ranked, ranking = order(column, tier, tokens)
    return (
        f"""
        select s.id, s.name, m.name, s.best_mbps
        from street s left join municipality m on m.id = s.municipality_id
        where {where}
        order by {ranked} s.ways desc, s.id
        limit %s
        """,
        tuple(taken + ranking + [limit]),
    )


def like_literal(text: str) -> str:
    """Escape LIKE wildcards, so typing % searches for a percent sign."""
    for character in ("\\", "%", "_"):
        text = text.replace(character, "\\" + character)
    return text


def results(hits: list[tuple[Any, ...]], match: str) -> list[Result]:
    return [
        Result(
            kind=row[0], id=row[1], name=row[2], street_no=row[3], locality=row[4],
            municipality=row[5], postcode=row[6], premises=row[7], best_mbps=row[8],
            match=match,
        )
        for row in hits
    ]


@app.get("/search", response_model=list[Result], tags=["search"])
def search(
    q: str = Query(min_length=MIN_QUERY, description="street, optionally with a town"),
    limit: int = Query(8, ge=1, le=MAX_RESULTS),
    kind: Literal["any", "street"] = Query(
        "any", description="street: streets only, for a map that has no doors on it"
    ),
) -> list[Result]:
    """Addresses and streets, in Greek or Greeklish, folded the way the index was built."""
    # One connection for all tiers. A keystroke can run nine queries, and checking out a
    # connection per query cost pool bookkeeping and left prepared statements on another.
    with pool.connection() as conn:
        return searched(conn, q, limit, kind)


def searched(
    conn: psycopg.Connection[Any], q: str, limit: int, kind: Literal["any", "street"]
) -> list[Result]:
    def ask(sql: str, params: tuple[object, ...]) -> list[tuple[Any, ...]]:
        return conn.execute(sql, params).fetchall()

    greeklish = is_greeklish(q)
    folded = from_latin(street_key(q)) if greeklish else street_key(q)
    street, number = split_number(folded)
    term = Term(folded=like_literal(street), number=number)

    # an address key includes the locality, a street key is only the name
    sources = (
        (street_sql, "latin_key" if greeklish else "name_fold"),
    ) if kind == "street" else (
        (address_sql, "latin_key" if greeklish else "search_key"),
        (street_sql, "latin_key" if greeklish else "name_fold"),
    )

    hits: list[Result] = []

    # a name without a number is a question about the street, so streets go first
    if kind == "any" and term.number is None:
        for tier in TIERS:
            sql, taken = street_sql("latin_key" if greeklish else "name_fold", tier, term, STREET_SLOTS)
            hits += results(ask(sql, taken), tier)
            # stop at the first tier that answered
            if hits:
                break
        hits = hits[:STREET_SLOTS]

    seen = {(row.kind, row.id) for row in hits}
    for tier in TIERS:
        for builder, column in sources:
            remaining = limit - len(hits)
            if remaining <= 0:
                break
            sql, taken = builder(column, tier, term, remaining)
            for row in results(ask(sql, taken), tier):
                if (row.kind, row.id) in seen:
                    continue
                seen.add((row.kind, row.id))
                hits.append(row)
        if len(hits) >= limit:
            break
    if kind == "street":
        # A map has no doors, so a typed number picks its street instead of offering a door
        # nobody can click.
        return hits[:limit]
    return offer_the_number(conn, hits, term, "latin_key" if greeklish else "name_fold", limit)


def offer_the_number(
    conn: psycopg.Connection[Any], hits: list[Result], term: Term, key: str, limit: int
) -> list[Result]:
    """The typed number on a street we know, filed or not.

    Filed addresses come first. One that exists beats one we'd have to make.
    """
    if term.number is None:
        return hits[:limit]
    if any(r.kind == "address" and r.street_no == term.number for r in hits):
        return hits[:limit]

    proposals: list[Result] = []
    for tier in TIERS:
        if proposals:
            break
        sql, taken = proposable(key, tier, term, PROPOSALS)
        proposals = [
            Result(
                kind="proposed", id=row[0], name=row[1], street_no=term.number,
                locality=None, municipality=row[2], postcode=None, premises=None,
                best_mbps=row[3], match="asked", street_id=row[0],
            )
            for row in conn.execute(sql, taken).fetchall()
        ]
    # a street offered both as itself and as a door on it: keep the door, it's what was asked
    offered = {p.id for p in proposals}
    rest = [r for r in hits if not (r.kind == "street" and r.id in offered)]
    return (proposals + rest)[:limit]


# sold_mbps is the retail speed for the line, capped by the normally available band where one
# was filed. It's the figure 110 paints the map with, so a panel can't disagree with its colour.
OFFER_COLUMNS = """
    p.code, p.display_name, ac.technology, ac.family, ac.matched_by, ac.avail_date,
    ip.code, sb.id, sb.min_mbps, sb.max_mbps, sb.label,
    least(t.sold_mbps, coalesce(nb.max_mbps, sb.max_mbps))
"""

# The street is looked up here and not in search, which runs per keystroke. Someone looking
# at one address isn't typing.
ADDRESS_DETAIL = """
select a.id, a.street, a.street_no, a.locality, m.name, a.postcode,
       a.premises, a.connected, a.vhcn, st_x(a.geom::geometry), st_y(a.geom::geometry),
       s.id
from address a
left join municipality m on m.id = a.municipality_id
left join street s on s.id = a.street_id
where a.id = %s
"""

ADDRESS_OFFERS = f"""
select {OFFER_COLUMNS}
from address_coverage ac
join provider p on p.id = ac.provider_id
join technology t on t.code = ac.technology
left join provider ip on ip.id = ac.infra_provider_id
left join speed_band sb on sb.id = ac.speed_band_id
left join speed_band nb on nb.id = ac.normal_band_id
where ac.address_id = %s
order by t.sold_mbps desc nulls last, p.code
"""

# The shape as well as the box: the box aims the camera, the highlight runs along the street,
# and a street that bends isn't a rectangle. Merged first.
STREET_DETAIL = """
select s.id, s.name, m.name, s.highway, s.ways,
       st_xmin(box), st_ymin(box), st_xmax(box), st_ymax(box),
       st_asgeojson(st_simplify(st_linemerge(s.geom::geometry), 0.00002), 6)
from street s
left join municipality m on m.id = s.municipality_id
cross join lateral (select st_envelope(s.geom::geometry) as box) extent
where s.id = %s
"""

# A street's offers: doors on it, cabinets it crosses, built fiber beside it. 110 walks those
# routes to paint the map and stores one row per operator and technology, so the panel reads
# exactly what the colour came from, in one index lookup. Walked live it took 180 ms on Ερμού.
STREET_OFFERS = """
select p.code, p.display_name, so.technology, so.family, so.matched, so.avail_date,
       ip.code, sb.id, sb.min_mbps, sb.max_mbps, sb.label, so.sold_mbps
from street_offer so
join provider p on p.id = so.provider_id
left join provider ip on ip.id = so.infra_provider_id
left join speed_band sb on sb.id = so.speed_band_id
where so.street_id = %s
order by p.code, so.technology
"""


class Speed(BaseModel):
    band: int
    min_mbps: float | None = Field(description="null on the open-ended bottom band")
    max_mbps: float | None = Field(description="null on the open-ended top band")
    label: str


class Offer(BaseModel):
    provider: str
    provider_name: str
    technology: str
    family: str
    matched_by: str = Field(
        description=(
            "point for a filing here, area for a cabinet, built for fiber in the "
            "ground that the register never gave an address"
        )
    )
    available_from: date | None
    infra_provider: str | None = Field(description="who built it, when not the seller")
    speed: Speed | None = Field(description="null when the operator filed no speed")
    sold_mbps: Decimal | None = Field(
        default=None,
        description=(
            "what this kind of line is retailed at, which is what the map is painted by. "
            "`speed` is the register's own band and is not what anything is drawn from"
        ),
    )


class AddressDetail(BaseModel):
    id: int
    street: str
    street_no: str | None
    locality: str | None
    municipality: str | None
    postcode: str | None
    premises: int | None
    connected: bool | None = Field(description="null when not filed, not false")
    vhcn: bool | None
    lon: float
    lat: float
    street_id: int | None = Field(
        default=None, description="the street this door is on, when it is one we hold"
    )
    offers: list[Offer]


class StreetDetail(BaseModel):
    id: int
    name: str
    municipality: str | None
    highway: str
    ways: int = Field(description="OSM ways merged into this street")
    bbox: tuple[float, float, float, float] = Field(
        description="west, south, east, north. A street has no point, only an extent"
    )
    shape: dict[str, Any] = Field(
        description="the street as GeoJSON, for drawing along rather than pointing at"
    )
    offers: list[Offer]


def offers(hits: list[tuple[Any, ...]]) -> list[Offer]:
    return [
        Offer(
            provider=row[0], provider_name=row[1], technology=row[2], family=row[3],
            matched_by=row[4], available_from=row[5], infra_provider=row[6],
            speed=None if row[7] is None else Speed(
                band=row[7], min_mbps=row[8], max_mbps=row[9], label=row[10]
            ),
            sold_mbps=row[11],
        )
        for row in hits
    ]


def one(sql: str, identifier: int, missing: str) -> tuple[Any, ...]:
    hits = rows(sql, (identifier,))
    if not hits:
        raise HTTPException(status_code=404, detail=missing)
    return hits[0]


@app.get("/addresses/{address_id}", response_model=AddressDetail, tags=["address"])
def address(address_id: int) -> AddressDetail:
    """Everything filed at one address, with each offer's evidence and freshness."""
    row = one(ADDRESS_DETAIL, address_id, "no such address")
    return AddressDetail(
        id=row[0], street=row[1], street_no=row[2], locality=row[3], municipality=row[4],
        postcode=row[5], premises=row[6], connected=row[7], vhcn=row[8],
        lon=row[9], lat=row[10], street_id=row[11],
        offers=offers(rows(ADDRESS_OFFERS, (address_id,))),
    )


# One address as a search row, so a freshly made address comes back in the shape the
# suggestion list already renders.
SEARCH_ONE = f"""
    select {ADDRESS_COLUMNS}
    from address a left join municipality m on m.id = a.municipality_id
    where a.id = %s
"""


@app.get("/streets/{street_id}", response_model=StreetDetail, tags=["street"])
def street(street_id: int) -> StreetDetail:
    """A street where no address is filed: coverage comes from the cabinets it crosses."""
    row = one(STREET_DETAIL, street_id, "no such street")
    return StreetDetail(
        id=row[0], name=row[1], municipality=row[2], highway=row[3], ways=row[4],
        bbox=(row[5], row[6], row[7], row[8]),
        shape=json.loads(row[9]),
        offers=offers(rows(STREET_OFFERS, (street_id,))),
    )


class Asking(BaseModel):
    street_no: str = Field(min_length=1, max_length=16, description="as the reader typed it")


@app.post(
    "/streets/{street_id}/addresses",
    response_model=Result,
    status_code=201,
    tags=["street"],
)
def ask_for(street_id: int, term: Asking) -> Result:
    """Make the address at this number, so it can be probed and kept like any other.

    The register knows the street and not the number.
    """
    number = fold(term.street_no)
    # a field of spaces passes the length check and folds to nothing
    if not number:
        raise HTTPException(422, "no house number")
    with pool.connection() as conn:
        address_id = propose(conn, street_id, number)
        if address_id is None:
            raise HTTPException(404, "no such street")
        conn.commit()
        hits = conn.execute(SEARCH_ONE, (address_id,)).fetchone()

    if hits is None:
        raise HTTPException(404, "no such address")
    return results([hits], "asked")[0]


@app.post("/reports", response_model=Report, status_code=201, tags=["report"])
def report(filed: ReportIn) -> Report:
    """Record that something here looks wrong.

    Rate limiting belongs at the reverse proxy rather than in process, where it would be per
    worker and reset on deploy.
    """
    try:
        with pool.connection() as conn:
            row = conn.execute(FILED, (
                filed.kind, filed.detail, filed.address_id,
                filed.provider_id, filed.plan_id, filed.contact,
            )).fetchone()
    except psycopg.errors.ForeignKeyViolation as unknown:
        # an unknown id is a bad report, not a server error
        raise HTTPException(422, "unknown address, provider or plan") from unknown
    if row is None:
        raise HTTPException(500, "report not recorded")
    return Report(id=row[0], created_at=row[1])


def names(conn: psycopg.Connection[Any], codes: list[str]) -> dict[str, str]:
    """Display names for operator codes.

    Uses the caller's connection. It used to take a second one from the pool while holding the
    first, so four concurrent requests on a pool of four each waited forever.
    """
    hits = conn.execute("select code, display_name from provider where code = any(%s)", (codes,)).fetchall()
    return {str(code): str(display) for code, display in hits}


# The three retailers we can ask. Everyone else comes from the register and what they publish,
# since they have no checker to ask.
RETAIL = ["TELEKOM", "VODAFONE", "NOVA"]


class Cost(BaseModel):
    """A monthly cost in its parts, so a card can say why a cheap headline is not cheap."""

    total: Decimal
    recurring: Decimal
    upfront: Decimal = Field(description="setup and equipment, spread over the window")
    complete: bool = Field(
        default=True,
        description=(
            "false when a one-off was never published, which makes total a floor: "
            "the offer costs this or more. The monthly rate is always known"
        ),
    )


class Buyable(BaseModel):
    provider: str = Field(description="the code every join uses")
    provider_name: str = Field(description="what the reader is shown")
    plan: str
    technology: str
    family: str
    expected_mbps: Decimal | None = Field(description="null when nothing here can say")
    data_cap_gb: int | None = Field(description="null is unlimited, not unknown")
    cost: Cost = Field(description="always a figure. Cost.complete says whether it is exact")
    basis: str = Field(description="quoted, measured, filed or advertised")
    tests: int = Field(description="measurements behind it, zero when it rests on none")
    confidence: float = Field(description="evidence from tests alone, so a quote has none")
    enough: bool = Field(description="covers an ordinary household, on speed and allowance")
    why: str


class Operator(BaseModel):
    provider: str
    provider_name: str
    known: str = Field(description="how this operator's answer was arrived at")
    state: str = Field(description="healthy, degraded, broken, untried, or blocked by its bot protection")
    says: str = Field(description="what to tell the reader when it is not answering")
    answered_on: date | None = Field(
        default=None,
        description="when it last gave this address a real answer, for saying how old a cached one is",
    )


class Options(BaseModel):
    address_id: int
    need_mbps: Decimal = Field(description="the bar used, which the caller may move")
    known: dict[str, str] = Field(description="per operator: how the answer was arrived at")
    operators: list[Operator] = Field(
        description="an operator missing from a comparison is a worse lie than a visible gap"
    )
    options: list[Buyable]


# When each operator last gave this door a real answer. A refusal is an answer too, so this
# reads the attempts, not availability, which only ever holds offers.
ANSWERED = """
select p.code, max(a.attempted_at)::date
from probe_attempt a
join provider p on p.id = a.provider_id
where a.address_id = %s and a.ok and p.code = any(%s)
group by p.code
"""


# Spreading a one-off over 24 months rarely lands on a cent. The arithmetic stays exact and
# rounds once, here.
CENTS = Decimal("0.01")


def cents(amount: object) -> Decimal:
    return Decimal(str(amount)).quantize(CENTS, rounding=ROUND_HALF_UP)


def priced(total: object, recurring: object, upfront: object, complete: bool) -> Cost:
    return Cost(total=cents(total), recurring=cents(recurring), upfront=cents(upfront), complete=complete)


@app.get("/addresses/{address_id}/options", response_model=Options, tags=["address"])
def address_options(
    address_id: int,
    need_mbps: Annotated[Decimal, Query(gt=0, le=10000)] = ENOUGH_MBPS,
) -> Options:
    """What can be bought here, best first, from what is already known.

    Nothing is asked of an operator on this path.
    """
    with pool.connection() as conn:
        hits = conn.execute("select 1 from address where id = %s", (address_id,)).fetchone()
        if hits is None:
            raise HTTPException(404, "no such address")
        now = datetime.now(UTC)
        known = verdicts(conn, address_id, RETAIL, now=now)
        states = adapter_state(conn, RETAIL, now)
        display = names(conn, RETAIL)
        ranked = rank(buyable(conn, address_id), need=need_mbps)
        answered: dict[str, date] = dict(conn.execute(ANSWERED, (address_id, RETAIL)).fetchall())

    return Options(
        address_id=address_id,
        need_mbps=need_mbps,
        known=known,
        operators=[
            Operator(
                provider=code,
                provider_name=display.get(code, code),
                known=known.get(code, "unknown"),
                state=states[code].state,
                says=states[code].says,
                answered_on=answered.get(code),
            )
            for code in sorted(states)
        ],
        options=[
            Buyable(
                provider=r.option.provider,
                provider_name=r.option.provider_name,
                plan=r.option.plan,
                technology=r.option.technology,
                family=r.option.family,
                expected_mbps=r.option.expected_mbps,
                data_cap_gb=r.option.data_cap_gb,
                cost=priced(
                    r.option.cost.total, r.option.cost.recurring, r.option.cost.upfront,
                    r.option.cost.complete,
                ),
                basis=r.option.basis,
                tests=r.option.tests,
                confidence=r.option.confidence,
                enough=r.enough,
                why=r.why,
            )
            for r in ranked
        ],
    )


class Probed(BaseModel):
    provider: str
    asked: bool = Field(description="false when the operator was inside its backoff")
    reached: bool = Field(description="false when the checker could not be reached at all")
    serviceable: bool | None = Field(description="null when nothing conclusive came back")
    detail: str | None


ADAPTERS: dict[str, Callable[[], Adapter]] = {"TELEKOM": Cosmote, "VODAFONE": Vodafone, "NOVA": Nova}


@app.post("/addresses/{address_id}/probe", response_model=list[Probed], tags=["address"])
def address_probe(
    address_id: int,
    provider: Annotated[
        list[str] | None,
        Query(description="ask only these, or omit to ask every operator that is due"),
    ] = None,
) -> list[Probed]:
    """Ask the operators that are due, and keep what they say.

    One operator at a time is the caller's choice, and the reason it exists: a checker takes
    between two and eight seconds.
    """
    wanted = RETAIL if provider is None else [p for p in provider if p in ADAPTERS]
    if not wanted:
        raise HTTPException(422, "no operator by that name")

    with pool.connection() as conn:
        target = target_for(conn, address_id)
        if target is None:
            raise HTTPException(404, "no such address")
        term: list[Adapter] = [ADAPTERS[code]() for code in wanted]
        answers = refresh(conn, target, term, datetime.now(UTC))

    # An operator in backoff isn't asked and refresh returns nothing for it. Report it as not
    # asked so it doesn't silently vanish from the answer.
    probed: list[Probed] = []
    for code in sorted(set(wanted)):
        answer = answers.get(code)
        if answer is None:
            probed.append(Probed(provider=code, asked=False, reached=False, serviceable=None, detail=None))
            continue
        probed.append(Probed(
            provider=code,
            asked=True,
            reached=answer.result is not None,
            serviceable=(
                None if answer.result is None or not answer.result.conclusive
                else answer.result.serviceable
            ),
            detail=answer.error,
        ))
    return probed


@app.get("/health/adapters", response_model=list[Operator], tags=["meta"])
def adapter_health() -> list[Operator]:
    """How each operator's checker is faring, derived from what happened when it was asked.

    Not stored anywhere: a status field is one more thing that can be stale while the thing
    it describes has moved on.
    """
    with pool.connection() as conn:
        states = adapter_state(conn, RETAIL, datetime.now(UTC))
        display = names(conn, RETAIL)
    return [
        Operator(
            provider=code,
            provider_name=display.get(code, code),
            known="-",
            state=states[code].state,
            says=states[code].says,
        )
        for code in sorted(states)
    ]
