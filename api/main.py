"""JSON over the register. Computes nothing: it returns stored state, including the state of

Reads, with one exception.
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

pool = ConnectionPool(settings.dsn, min_size=1, max_size=4, open=False)


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


class Health(BaseModel):
    ok: bool
    addresses: int = Field(description="rows in the address index")
    offers: int = Field(description="rows in address_coverage")


def rows(
    sql: str, params: tuple[object, ...] | dict[str, object] = ()
) -> list[tuple[Any, ...]]:
    with pool.connection() as conn:
        return conn.execute(sql, params).fetchall()


# What a person is allowed to say went wrong. Free text is capped rather than trusted:
# it is stored as typed and never read as anything but text.
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
    row = rows(
        "select (select count(*) from address), (select count(*) from address_coverage)"
    )
    addresses, offers = row[0]
    return Health(ok=True, addresses=addresses, offers=offers)


MIN_QUERY = 2
MAX_RESULTS = 20

# The fastest thing known to reach this address, for the dot beside it. Two sources: what an
# operator has told us directly, and what the best line into the building is sold at.
BEST_MBPS = """
    greatest(
        (select max(v.max_down_mbps) from availability v
         where v.address_id = a.id and v.serviceable),
        (select max(t.sold_mbps) from address_coverage ac
         join technology t on t.code = ac.technology
         where ac.address_id = a.id and ac.family <> 'wireless')
    )
"""

ADDRESS_COLUMNS = f"""
    'address', a.id, a.street, a.street_no, a.locality, m.name, a.postcode, a.premises,
    {BEST_MBPS}
"""

# A street's best is the best of the addresses on it, worked out by the build rather than
# here: asking it per keystroke cost 173ms against a tier that answers in a third of one.
STREET_COLUMNS = """
    'street', s.id, s.name, null, null, m.name, null, null, s.best_mbps
"""

# Three tiers, widening only when the one above has not filled the page.
TIERS = ("prefix", "word", "fuzzy")

# How many streets a name with no number is answered with before the doors on it.
STREET_SLOTS = 2

# How many streets a bare number is offered on. More than two is a list of guesses.
PROPOSALS = 2


# The register files a bare dash where it holds no street name: 70 addresses of it.
NAMELESS = "a.street <> '-'"


@dataclass(frozen=True)
class Term:
    """A query taken apart: what to match on, and the house number to prefer."""

    folded: str
    number: str | None


def condition(column: str, tier: str, tokens: list[str]) -> tuple[str, list[object]]:
    """The where clause for one tier, and the values it takes.

    The word tier asks for every token separately and in no particular order, because Greek
    street names are filed both ways round.
    """
    joined = " ".join(tokens)
    prefix, anywhere = joined + "%", "% " + joined + "%"
    if tier == "prefix":
        return f"{column} like %s", [prefix]
    if tier == "word":
        # Each token at the start of the key or at the start of a word inside it.
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
    """Within a tier every row matched equally well, so rank by size, not by spelling."""
    if tier != "fuzzy":
        return "", []
    return f"similarity({column}, %s) desc,", [" ".join(tokens)]


# How many distinct spellings a typo is allowed to have meant. The fuzzy tier matches against the
# spellings rather than against the doors, and then fetches the doors on the spellings it liked.
KEY_SLOTS = 20


def fuzzy_address_sql(key: str, term: Term, limit: int) -> tuple[str, tuple[object, ...]]:
    """The fuzzy tier, asked of the spellings rather than of every door that carries one.

    It used to run `search_key % '…'` straight over all 1.8M addresses and it was the slowest
    thing on the site by an order of magnitude.
    """
    tokens = term.folded.split(" ")
    joined = " ".join(tokens)
    prefix, anywhere = joined + "%", "% " + joined + "%"
    wanted, number = ("a.street_no = %s desc, ", [term.number]) if term.number else ("", [])
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
    # The number the reader typed, ahead of every other way of ordering the street's
    # addresses: it is the most specific thing they said and it was being thrown away.
    wanted, number = ("a.street_no = %s desc, ", [term.number]) if term.number else ("", [])
    return (
        f"""
    select {ADDRESS_COLUMNS}
    from address a left join municipality m on m.id = a.municipality_id
    where {NAMELESS} and {where}
    order by {wanted}{ranked} a.premises desc nulls last, a.id
    limit %s
    """,
        tuple(taken + number + ranking + [limit]),
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
    locality: str | None = Field(description="as the register filed it")
    municipality: str | None
    postcode: str | None
    premises: int | None = Field(description="dwellings passed, null when not filed")
    best_mbps: Decimal | None = Field(
        description="the fastest known to reach here; null is not filed, not zero"
    )
    match: str = Field(description="prefix, word, fuzzy or asked")
    street_id: int | None = Field(
        default=None,
        description="for a proposed address, the street to ask for it on",
    )


def proposable(key: str, tier: str, term: Term, limit: int) -> tuple[str, tuple[object, ...]]:
    """Streets a number could be on, looked up in their own right.

    The suggestion list fills with addresses first and a street may never reach the page, so
    a proposal cannot be built out of whatever the tiers happened to return.
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
    """Escape the wildcards, so a user typing % searches for a percent sign."""
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
    greeklish = is_greeklish(q)
    folded = from_latin(street_key(q)) if greeklish else street_key(q)
    street, number = split_number(folded)
    term = Term(folded=like_literal(street), number=number)

    # The two tables spell the same idea differently: an address key carries the locality, a
    # street key is the name alone.
    sources = (
        (street_sql, "latin_key" if greeklish else "name_fold"),
    ) if kind == "street" else (
        (address_sql, "latin_key" if greeklish else "search_key"),
        (street_sql, "latin_key" if greeklish else "name_fold"),
    )

    hits: list[Result] = []

    # A name with no number on it is a question about the street, so the street answers first.
    if kind == "any" and term.number is None:
        for tier in TIERS:
            sql, taken = street_sql(
                "latin_key" if greeklish else "name_fold", tier, term, STREET_SLOTS
            )
            hits += results(rows(sql, taken), tier)
            # The best tier that answered at all, and no further.
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
            for row in results(rows(sql, taken), tier):
                if (row.kind, row.id) in seen:
                    continue
                seen.add((row.kind, row.id))
                hits.append(row)
        if len(hits) >= limit:
            break
    if kind == "street":
        # A map has no doors on it, so a number the reader typed picks the street it is on
        # rather than offering to make a door nobody can click.
        return hits[:limit]
    return offer_the_number(hits, term, "latin_key" if greeklish else "name_fold", limit)


def offer_the_number(
    hits: list[Result], term: Term, key: str, limit: int
) -> list[Result]:
    """The number the reader typed, on a street we know, whether or not it is filed.

    Held addresses come first: one that exists is worth more than one we would have to make.
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
            for row in rows(sql, taken)
        ]
    # A street offered both as itself and as a door on it is two answers to one question,
    # and the door is the one that was asked for.
    offered = {p.id for p in proposals}
    rest = [r for r in hits if not (r.kind == "street" and r.id in offered)]
    return (proposals + rest)[:limit]


# One shape for both, but only address_coverage records how the match was made: for a
# street it is an area by construction, because a street has no point of its own.
AREA_MATCH = "'area'"

# sold_mbps is what this kind of line is retailed at, and it is the figure the map is painted with
# and the panel shows.
OFFER_COLUMNS = """
    p.code, p.display_name, ac.technology, ac.family, {matched}, ac.avail_date,
    ip.code, sb.id, sb.min_mbps, sb.max_mbps, sb.label, t.sold_mbps
"""

# The street is resolved here rather than in the search, which answers per keystroke and
# is measured in tenths of a millisecond. A reader looking at one address is not typing.
ADDRESS_DETAIL = """
select a.id, a.street, a.street_no, a.locality, m.name, a.postcode,
       a.premises, a.connected, a.vhcn, st_x(a.geom::geometry), st_y(a.geom::geometry),
       s.id
from address a
left join municipality m on m.id = a.municipality_id
left join street s
       on s.municipality_id = a.municipality_id and s.name_fold = a.street_fold
where a.id = %s
"""

ADDRESS_OFFERS = f"""
select {OFFER_COLUMNS.format(matched="ac.matched_by")}
from address_coverage ac
join provider p on p.id = ac.provider_id
join technology t on t.code = ac.technology
left join provider ip on ip.id = ac.infra_provider_id
left join speed_band sb on sb.id = ac.speed_band_id
where ac.address_id = %s
order by t.sold_mbps desc nulls last, p.code
"""

# The shape as well as the box. A box says where to point the camera. The highlight has to run
# along the street itself, and a street that bends is not its own rectangle. Merged first.
STREET_DETAIL = """
select s.id, s.name, m.name, s.highway, s.ways,
       st_xmin(box), st_ymin(box), st_xmax(box), st_ymax(box),
       st_asgeojson(st_simplify(st_linemerge(s.geom::geometry), 0.00002), 6)
from street s
left join municipality m on m.id = s.municipality_id
cross join lateral (select st_envelope(s.geom::geometry) as box) extent
where s.id = %s
"""

# How large a filed area may be and still say anything about one street. Not a number here.
CABINET = "cabinet_m2()"

# A street has no address of its own, so its offers are the cabinets it runs through. distinct on,
# because one road crosses several cabinets of the same operator.
STREET_OFFERS = f"""
select distinct on (code, technology) * from (
    select {OFFER_COLUMNS.format(matched=AREA_MATCH)}
    from street s
    join coverage_area ac on st_intersects(ac.geom_2d, s.geom::geometry)
    join provider p on p.id = ac.provider_id
    join technology t on t.code = ac.technology
    left join provider ip on ip.id = ac.infra_provider_id
    left join speed_band sb on sb.id = ac.speed_band_id
    where s.id = %s
      and ac.area_m2 <= {CABINET}

    union all

    select {OFFER_COLUMNS.format(matched="'point'")}
    from street s
    join address a
      on a.municipality_id = s.municipality_id and a.street_fold = s.name_fold
    join address_coverage ac on ac.address_id = a.id
    join provider p on p.id = ac.provider_id
    join technology t on t.code = ac.technology
    left join provider ip on ip.id = ac.infra_provider_id
    left join speed_band sb on sb.id = ac.speed_band_id
    -- Fixed lines only, the same rule the street's own figure follows: an operator whose
    -- 5G reaches everywhere is not an operator that reaches this street, and listing it
    -- here would put the same gigabit on every road in the country.
    where s.id = %s and ac.family <> 'wireless'
) reached (
    code, display_name, technology, family, matched, avail_date,
    infra_code, band_id, min_mbps, max_mbps, label, sold_mbps
)
order by code, technology, sold_mbps desc nulls last
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
    matched_by: str = Field(description="point for a filing here, area for a cabinet")
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
        description="west, south, east, north — a street has no point, only an extent"
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


# The search row for one address, so an address just made comes back in the shape the
# suggestion list already knows how to render.
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
        offers=offers(rows(STREET_OFFERS, (street_id, street_id))),
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

    The only write in the API. Rate limiting belongs at the reverse proxy rather than in
    process, where it would be per worker and reset on deploy.
    """
    try:
        with pool.connection() as conn:
            row = conn.execute(FILED, (
                filed.kind, filed.detail, filed.address_id,
                filed.provider_id, filed.plan_id, filed.contact,
            )).fetchone()
    except psycopg.errors.ForeignKeyViolation as unknown:
        # An id we do not have is a mistaken report, not a server fault.
        raise HTTPException(422, "unknown address, provider or plan") from unknown
    if row is None:
        raise HTTPException(500, "report not recorded")
    return Report(id=row[0], created_at=row[1])


def names(conn: object, codes: list[str]) -> dict[str, str]:
    """What each operator is called where a reader can see it."""
    hits = rows("select code, display_name from provider where code = any(%s)", (codes,))
    return {str(code): str(display) for code, display in hits}


# The three that sell to households and can be asked. The rest are read from the register
# and from what they publish, because there is nothing of theirs to ask.
RETAIL = ["OTE", "VODAFONE", "NOVA"]


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
    cost: Cost = Field(description="always a figure; see Cost.complete for whether it is exact")
    basis: str = Field(description="quoted, measured, filed or advertised")
    tests: int = Field(description="measurements behind it, zero when it rests on none")
    confidence: float = Field(description="evidence from tests alone; a quote has none")
    enough: bool = Field(description="covers an ordinary household, on speed and allowance")
    why: str


class Operator(BaseModel):
    provider: str
    provider_name: str
    known: str = Field(description="how this operator's answer was arrived at")
    state: str = Field(description="healthy, degraded, broken or untried")
    says: str = Field(description="what to tell the reader when it is not answering")


class Options(BaseModel):
    address_id: int
    need_mbps: Decimal = Field(description="the bar used, which the caller may move")
    known: dict[str, str] = Field(description="per operator: how the answer was arrived at")
    operators: list[Operator] = Field(
        description="an operator missing from a comparison is a worse lie than a visible gap"
    )
    options: list[Buyable]


# Blending a lump sum across two years is an exact division and rarely lands on a cent.
# The arithmetic stays exact and the answer is rounded once, here, where it is read.
CENTS = Decimal("0.01")


def cents(amount: object) -> Decimal:
    return Decimal(str(amount)).quantize(CENTS, rounding=ROUND_HALF_UP)


def priced(total: object, recurring: object, upfront: object, complete: bool) -> Cost:
    return Cost(
        total=cents(total), recurring=cents(recurring), upfront=cents(upfront),
        complete=complete,
    )


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


ADAPTERS: dict[str, Callable[[], Adapter]] = {
    "OTE": Cosmote,
    "VODAFONE": Vodafone,
    "NOVA": Nova,
}


@app.post("/addresses/{address_id}/probe", response_model=list[Probed], tags=["address"])
def address_probe(
    address_id: int,
    provider: Annotated[
        list[str] | None,
        Query(description="ask only these; omit to ask every operator that is due"),
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

    return [
        Probed(
            provider=code,
            asked=True,
            reached=answer.result is not None,
            serviceable=(
                None if answer.result is None or not answer.result.conclusive
                else answer.result.serviceable
            ),
            detail=answer.error,
        )
        for code, answer in sorted(answers.items())
    ]


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
