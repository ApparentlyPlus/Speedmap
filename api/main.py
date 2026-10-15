"""JSON over the register. Read only except reports, asked-for addresses and probe answers."""

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

# jit off: queries here take a ms or two, and a jit compile on the Pi takes 100x that
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
    row = rows("select (select count(*) from address), (select count(*) from address_coverage)")
    addresses, offers = row[0]
    return Health(ok=True, addresses=addresses, offers=offers)


MIN_QUERY = 2
MAX_RESULTS = 20

# the dot beside an address, capped like 110 caps a street
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

# both stored by the build, the locality tells two runs of a name apart (7,320 names)
STREET_COLUMNS = """
    'street', s.id, s.name, null, s.locality, m.name, null, null, s.best_mbps
"""

TIERS = ("prefix", "word", "fuzzy")  # widening only while the page isn't full

STREET_SLOTS = 2  # for a name typed without a number
PROPOSALS = 2  # more than two is guessing

# 70 addresses have "-" for a street
NAMELESS = "a.street <> '-'"


@dataclass(frozen=True)
class Term:
    folded: str
    number: str | None


# nulls last matters, 126,000 doors have no number and desc puts nulls first
NUMBER_FIRST = "(a.street_no = %s) desc nulls last, "


def condition(column: str, tier: str, tokens: list[str]) -> tuple[str, list[object]]:
    joined = " ".join(tokens)
    prefix, anywhere = joined + "%", "% " + joined + "%"
    if tier == "prefix":
        return f"{column} like %s", [prefix]
    if tier == "word":
        # tokens in any order, names get filed both ways round
        each = " and ".join(f"({column} like %s or {column} like %s)" for _ in tokens)
        vals: list[object] = []
        for t in tokens:
            vals += [t + "%", "% " + t + "%"]
        return f"{each} and not ({column} like %s)", [*vals, prefix]
    return (
        f"{column} %% %s and not ({column} like %s) and not ({column} like %s)",
        [joined, prefix, anywhere],
    )


def order(column: str, tier: str, tokens: list[str]) -> tuple[str, list[object]]:
    if tier != "fuzzy":
        return "", []
    return f"similarity({column}, %s) desc,", [" ".join(tokens)]


KEY_SLOTS = 20  # distinct spellings a typo might have meant


def fuzzy_address_sql(key: str, term: Term, limit: int) -> tuple[str, tuple[object, ...]]:
    # over distinct spellings, % on all 1.8M doors was the slowest thing on the site
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
    wanted, number = (NUMBER_FIRST, [term.number]) if term.number else ("", [])
    # pick the page of ids off the index first, two letters match 77,000 doors
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
    locality: str | None = Field(description="as filed for a door, the doors' majority for a street")
    municipality: str | None
    postcode: str | None
    premises: int | None = Field(description="dwellings passed")
    best_mbps: Decimal | None = Field(description="null if nothing's filed")
    match: str = Field(description="prefix, word, fuzzy or asked")
    street_id: int | None = Field(default=None, description="for a proposed address")


def proposable(key: str, tier: str, term: Term, limit: int) -> tuple[str, tuple[object, ...]]:
    # own query, the tiers can fill the page before a street shows
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
    for c in ("\\", "%", "_"):
        text = text.replace(c, "\\" + c)
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
    kind: Literal["any", "street"] = Query("any", description="street: streets only, for the map"),
) -> list[Result]:
    """Addresses and streets, in Greek or Greeklish."""
    # one connection for up to nine queries
    with pool.connection() as conn:
        return searched(conn, q, limit, kind)


def searched(conn: psycopg.Connection[Any], q: str, limit: int, kind: Literal["any", "street"]) -> list[Result]:
    def ask(sql: str, params: tuple[object, ...]) -> list[tuple[Any, ...]]:
        return conn.execute(sql, params).fetchall()

    greeklish = is_greeklish(q)
    folded = from_latin(street_key(q)) if greeklish else street_key(q)
    street, number = split_number(folded)
    term = Term(folded=like_literal(street), number=number)

    # address keys include the locality, street keys don't
    sources = (
        (street_sql, "latin_key" if greeklish else "name_fold"),
    ) if kind == "street" else (
        (address_sql, "latin_key" if greeklish else "search_key"),
        (street_sql, "latin_key" if greeklish else "name_fold"),
    )

    hits: list[Result] = []

    # no number, so streets first
    if kind == "any" and term.number is None:
        for tier in TIERS:
            sql, taken = street_sql("latin_key" if greeklish else "name_fold", tier, term, STREET_SLOTS)
            hits += results(ask(sql, taken), tier)
            if hits:
                break
        hits = hits[:STREET_SLOTS]

    seen = {(r.kind, r.id) for r in hits}
    for tier in TIERS:
        for builder, column in sources:
            left = limit - len(hits)
            if left <= 0:
                break
            sql, taken = builder(column, tier, term, left)
            for r in results(ask(sql, taken), tier):
                if (r.kind, r.id) in seen:
                    continue
                seen.add((r.kind, r.id))
                hits.append(r)
        if len(hits) >= limit:
            break
    if kind == "street":
        return hits[:limit]  # no doors to click on the map
    return offer_the_number(conn, hits, term, "latin_key" if greeklish else "name_fold", limit)


def offer_the_number(conn: psycopg.Connection[Any], hits: list[Result], term: Term, key: str,
                     limit: int) -> list[Result]:
    """The typed number on a street we know, if it isn't already a filed address."""
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
    # drop the street when it's also proposed as a door
    offered = {p.id for p in proposals}
    rest = [r for r in hits if not (r.kind == "street" and r.id in offered)]
    return (proposals + rest)[:limit]


# last column is what 110 paints with, so the panel matches the colour
OFFER_COLUMNS = """
    p.code, p.display_name, ac.technology, ac.family, ac.matched_by, ac.avail_date,
    ip.code, sb.id, sb.min_mbps, sb.max_mbps, sb.label,
    least(t.sold_mbps, coalesce(nb.max_mbps, sb.max_mbps))
"""

# street join lives here, search runs per keystroke
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

# box for the camera, shape for the highlight
STREET_DETAIL = """
select s.id, s.name, m.name, s.highway, s.ways,
       st_xmin(box), st_ymin(box), st_xmax(box), st_ymax(box),
       st_asgeojson(st_simplify(st_linemerge(s.geom::geometry), 0.00002), 6)
from street s
left join municipality m on m.id = s.municipality_id
cross join lateral (select st_envelope(s.geom::geometry) as box) extent
where s.id = %s
"""

# stored by 110, walking the routes live took 180 ms on Ερμού
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
    matched_by: str = Field(description="point (filed here), area (cabinet) or built (unaddressed fiber)")
    available_from: date | None
    infra_provider: str | None = Field(description="who built it, when not the seller")
    speed: Speed | None = Field(description="null when the operator filed no speed")
    sold_mbps: Decimal | None = Field(default=None, description="retail speed of the line, what the map paints")


class AddressDetail(BaseModel):
    id: int
    street: str
    street_no: str | None
    locality: str | None
    municipality: str | None
    postcode: str | None
    premises: int | None
    connected: bool | None = Field(description="null when not filed")
    vhcn: bool | None
    lon: float
    lat: float
    street_id: int | None = Field(default=None, description="the street this door is on, if we have it")
    offers: list[Offer]


class StreetDetail(BaseModel):
    id: int
    name: str
    municipality: str | None
    highway: str
    ways: int = Field(description="OSM ways merged into this street")
    bbox: tuple[float, float, float, float] = Field(description="west, south, east, north")
    shape: dict[str, Any] = Field(description="GeoJSON line")
    offers: list[Offer]


def offers(hits: list[tuple[Any, ...]]) -> list[Offer]:
    return [
        Offer(
            provider=r[0], provider_name=r[1], technology=r[2], family=r[3],
            matched_by=r[4], available_from=r[5], infra_provider=r[6],
            speed=None if r[7] is None else Speed(band=r[7], min_mbps=r[8], max_mbps=r[9], label=r[10]),
            sold_mbps=r[11],
        )
        for r in hits
    ]


def one(sql: str, id_: int, missing: str) -> tuple[Any, ...]:
    hits = rows(sql, (id_,))
    if not hits:
        raise HTTPException(status_code=404, detail=missing)
    return hits[0]


@app.get("/addresses/{address_id}", response_model=AddressDetail, tags=["address"])
def address(address_id: int) -> AddressDetail:
    """Everything filed at one address."""
    row = one(ADDRESS_DETAIL, address_id, "no such address")
    return AddressDetail(
        id=row[0], street=row[1], street_no=row[2], locality=row[3], municipality=row[4],
        postcode=row[5], premises=row[6], connected=row[7], vhcn=row[8],
        lon=row[9], lat=row[10], street_id=row[11],
        offers=offers(rows(ADDRESS_OFFERS, (address_id,))),
    )


# shaped like a search row, for the suggestion list
SEARCH_ONE = f"""
    select {ADDRESS_COLUMNS}
    from address a left join municipality m on m.id = a.municipality_id
    where a.id = %s
"""


@app.get("/streets/{street_id}", response_model=StreetDetail, tags=["street"])
def street(street_id: int) -> StreetDetail:
    """A street and what reaches it."""
    row = one(STREET_DETAIL, street_id, "no such street")
    return StreetDetail(
        id=row[0], name=row[1], municipality=row[2], highway=row[3], ways=row[4],
        bbox=(row[5], row[6], row[7], row[8]),
        shape=json.loads(row[9]),
        offers=offers(rows(STREET_OFFERS, (street_id,))),
    )


class Asking(BaseModel):
    street_no: str = Field(min_length=1, max_length=16, description="as the reader typed it")


@app.post("/streets/{street_id}/addresses", response_model=Result, status_code=201, tags=["street"])
def ask_for(street_id: int, term: Asking) -> Result:
    """Make the address at this number on a street the register has without it."""
    number = fold(term.street_no)
    if not number:  # all spaces
        raise HTTPException(422, "no house number")
    with pool.connection() as conn:
        aid = propose(conn, street_id, number)
        if aid is None:
            raise HTTPException(404, "no such street")
        conn.commit()
        hit = conn.execute(SEARCH_ONE, (aid,)).fetchone()

    if hit is None:
        raise HTTPException(404, "no such address")
    return results([hit], "asked")[0]


@app.post("/reports", response_model=Report, status_code=201, tags=["report"])
def report(filed: ReportIn) -> Report:
    """Record that something here looks wrong."""
    try:
        with pool.connection() as conn:
            row = conn.execute(FILED, (
                filed.kind, filed.detail, filed.address_id,
                filed.provider_id, filed.plan_id, filed.contact,
            )).fetchone()
    except psycopg.errors.ForeignKeyViolation as e:
        raise HTTPException(422, "unknown address, provider or plan") from e
    if row is None:
        raise HTTPException(500, "report not recorded")
    return Report(id=row[0], created_at=row[1])


def names(conn: psycopg.Connection[Any], codes: list[str]) -> dict[str, str]:
    # caller's connection, taking a second one from a pool of 4 deadlocks
    hits = conn.execute("select code, display_name from provider where code = any(%s)", (codes,)).fetchall()
    return {str(code): str(display) for code, display in hits}


# the ones with a checker to ask
RETAIL = ["TELEKOM", "VODAFONE", "NOVA"]


class Cost(BaseModel):
    total: Decimal
    recurring: Decimal
    upfront: Decimal = Field(description="setup and equipment, spread over the window")
    complete: bool = Field(default=True, description="false if a one-off is unpublished, so total is a floor")


class Buyable(BaseModel):
    provider: str = Field(description="the code every join uses")
    provider_name: str = Field(description="what the reader is shown")
    plan: str
    technology: str
    family: str
    expected_mbps: Decimal | None
    data_cap_gb: int | None = Field(description="null is unlimited")
    cost: Cost
    basis: str = Field(description="quoted, measured, filed or advertised")
    tests: int
    confidence: float = Field(description="from speed tests only, a quote has none")
    enough: bool = Field(description="covers an ordinary household, speed and allowance")
    why: str


class Operator(BaseModel):
    provider: str
    provider_name: str
    known: str = Field(description="a decide verdict")
    state: str = Field(description="healthy, degraded, broken, untried or blocked")
    says: str = Field(description="for the reader, when it isn't answering")
    answered_on: date | None = Field(default=None, description="last real answer for this address")


class Options(BaseModel):
    address_id: int
    need_mbps: Decimal = Field(description="the bar used")
    known: dict[str, str] = Field(description="verdict per operator")
    operators: list[Operator]
    options: list[Buyable]


# refusals count, so attempts and not availability
ANSWERED = """
select p.code, max(a.attempted_at)::date
from probe_attempt a
join provider p on p.id = a.provider_id
where a.address_id = %s and a.ok and p.code = any(%s)
group by p.code
"""


# round once, at the end
CENTS = Decimal("0.01")


def cents(amount: object) -> Decimal:
    return Decimal(str(amount)).quantize(CENTS, rounding=ROUND_HALF_UP)


def priced(total: object, recurring: object, upfront: object, complete: bool) -> Cost:
    return Cost(total=cents(total), recurring=cents(recurring), upfront=cents(upfront), complete=complete)


@app.get("/addresses/{address_id}/options", response_model=Options, tags=["address"])
def address_options(address_id: int, need_mbps: Annotated[Decimal, Query(gt=0, le=10000)] = ENOUGH_MBPS) -> Options:
    """What can be bought here, best first. Asks no operator."""
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
    asked: bool = Field(description="false inside its backoff")
    reached: bool
    serviceable: bool | None = Field(description="null if inconclusive")
    detail: str | None


ADAPTERS: dict[str, Callable[[], Adapter]] = {"TELEKOM": Cosmote, "VODAFONE": Vodafone, "NOVA": Nova}


@app.post("/addresses/{address_id}/probe", response_model=list[Probed], tags=["address"])
def address_probe(
    address_id: int,
    provider: Annotated[list[str] | None, Query(description="omit for every operator that's due")] = None,
) -> list[Probed]:
    """Ask the operators that are due, 2 to 8 seconds each."""
    wanted = RETAIL if provider is None else [p for p in provider if p in ADAPTERS]
    if not wanted:
        raise HTTPException(422, "no operator by that name")

    with pool.connection() as conn:
        target = target_for(conn, address_id)
        if target is None:
            raise HTTPException(404, "no such address")
        adapters: list[Adapter] = [ADAPTERS[code]() for code in wanted]
        replies = refresh(conn, target, adapters, datetime.now(UTC))

    probed: list[Probed] = []
    for code in sorted(set(wanted)):
        r = replies.get(code)
        if r is None:  # in backoff, still listed
            probed.append(Probed(provider=code, asked=False, reached=False, serviceable=None, detail=None))
            continue
        probed.append(Probed(
            provider=code,
            asked=True,
            reached=r.result is not None,
            serviceable=None if r.result is None or not r.result.conclusive else r.result.serviceable,
            detail=r.error,
        ))
    return probed


@app.get("/health/adapters", response_model=list[Operator], tags=["meta"])
def adapter_health() -> list[Operator]:
    """How each operator's checker is doing, worked out from recent attempts."""
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
