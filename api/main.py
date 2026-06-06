"""JSON over the register. Computes nothing: it returns stored state, including the state
of not knowing.

Reads, with one exception. Everything here is best effort — a register that leaves three
quarters of its filings undated, a scrape that stopped where it stopped, a rate card that
asks three times what the market charges — so there is somewhere to say we got it wrong."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated, Any, Literal

import psycopg
from fastapi import FastAPI, HTTPException, Query
from psycopg_pool import ConnectionPool
from pydantic import BaseModel, Field

from db.settings import settings
from normalise.greeklish import from_latin, is_greeklish
from normalise.text import street_key
from probe.cosmote import Cosmote
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


def rows(sql: str, params: tuple[object, ...] = ()) -> list[tuple[Any, ...]]:
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
    counted = rows(
        "select (select count(*) from address), (select count(*) from address_coverage)"
    )
    addresses, offers = counted[0]
    return Health(ok=True, addresses=addresses, offers=offers)


MIN_QUERY = 2
MAX_RESULTS = 20

ADDRESS_COLUMNS = """
    'address', a.id, a.street, a.street_no, a.locality, m.name, a.postcode, a.premises
"""

STREET_COLUMNS = """
    'street', s.id, s.name, null, null, m.name, null, null
"""

# Three tiers, widening only when the one above has not filled the page. A prefix costs
# 0.3ms, a word-start match 11ms, and similarity ordering 445ms over 1.5M rows.
TIERS = ("prefix", "word", "fuzzy")


def address_sql(key: str, tier: str) -> str:
    return f"""
    select {ADDRESS_COLUMNS}
    from address a left join municipality m on m.id = a.municipality_id
    where {condition('a.' + key, tier)}
    order by {order('a.' + key, tier)} a.premises desc nulls last, a.id
    limit %s
    """


def street_sql(key: str, tier: str) -> str:
    return f"""
    select {STREET_COLUMNS}
    from street s left join municipality m on m.id = s.municipality_id
    where {condition('s.' + key, tier)}
    order by {order('s.' + key, tier)} s.ways desc, s.id
    limit %s
    """


def condition(column: str, tier: str) -> str:
    if tier == "prefix":
        return f"{column} like %s"
    if tier == "word":
        return f"{column} like %s and not ({column} like %s)"
    return f"{column} %% %s and not ({column} like %s) and not ({column} like %s)"


def order(column: str, tier: str) -> str:
    """Within a tier every row matched equally well, so rank by size, not by spelling."""
    return f"similarity({column}, %s) desc," if tier == "fuzzy" else ""


def params(tier: str, folded: str, prefix: str, anywhere: str, limit: int) -> tuple[object, ...]:
    if tier == "prefix":
        return (prefix, limit)
    if tier == "word":
        return (anywhere, prefix, limit)
    return (folded, prefix, anywhere, folded, limit)


class Result(BaseModel):
    kind: str = Field(description="address or street")
    id: int
    name: str
    street_no: str | None
    locality: str | None = Field(description="as the register filed it")
    municipality: str | None
    postcode: str | None
    premises: int | None = Field(description="dwellings passed, null when not filed")
    match: str = Field(description="prefix, word or fuzzy")


def like_literal(text: str) -> str:
    """Escape the wildcards, so a user typing % searches for a percent sign."""
    for character in ("\\", "%", "_"):
        text = text.replace(character, "\\" + character)
    return text


def results(found: list[tuple[Any, ...]], match: str) -> list[Result]:
    return [
        Result(
            kind=row[0], id=row[1], name=row[2], street_no=row[3], locality=row[4],
            municipality=row[5], postcode=row[6], premises=row[7], match=match,
        )
        for row in found
    ]


@app.get("/search", response_model=list[Result], tags=["search"])
def search(
    q: str = Query(min_length=MIN_QUERY, description="street, optionally with a town"),
    limit: int = Query(8, ge=1, le=MAX_RESULTS),
) -> list[Result]:
    """Addresses and streets, in Greek or Greeklish, folded the way the index was built."""
    greeklish = is_greeklish(q)
    folded = from_latin(street_key(q)) if greeklish else street_key(q)

    # The two tables spell the same idea differently: an address key carries the locality,
    # a street key is the name alone.
    sources = (
        (address_sql, "latin_key" if greeklish else "search_key"),
        (street_sql, "latin_key" if greeklish else "name_fold"),
    )

    escaped = like_literal(folded)
    prefix, anywhere = escaped + "%", "% " + escaped + "%"

    found: list[Result] = []
    for tier in TIERS:
        for builder, column in sources:
            remaining = limit - len(found)
            if remaining <= 0:
                return found
            found += results(
                rows(builder(column, tier), params(tier, folded, prefix, anywhere, remaining)),
                tier,
            )
    return found


# One shape for both, but only address_coverage records how the match was made: for a
# street it is an area by construction, because a street has no point of its own.
AREA_MATCH = "'area'"

OFFER_COLUMNS = """
    p.code, p.display_name, ac.technology, ac.family, {matched}, ac.avail_date,
    ip.code, sb.id, sb.min_mbps, sb.max_mbps, sb.label
"""

ADDRESS_DETAIL = """
select a.id, a.street, a.street_no, a.locality, m.name, a.postcode,
       a.premises, a.connected, a.vhcn, st_x(a.geom::geometry), st_y(a.geom::geometry)
from address a left join municipality m on m.id = a.municipality_id
where a.id = %s
"""

ADDRESS_OFFERS = f"""
select {OFFER_COLUMNS.format(matched="ac.matched_by")}
from address_coverage ac
join provider p on p.id = ac.provider_id
left join provider ip on ip.id = ac.infra_provider_id
left join speed_band sb on sb.id = ac.speed_band_id
where ac.address_id = %s
order by sb.min_mbps desc nulls last, p.code
"""

STREET_DETAIL = """
select s.id, s.name, m.name, s.highway, s.ways
from street s left join municipality m on m.id = s.municipality_id
where s.id = %s
"""

# A street has no address of its own, so its offers are the cabinets it runs through.
# distinct on, because one road crosses several cabinets of the same operator.
# The alias is ac in both queries so the shared column list resolves in each.
STREET_OFFERS = f"""
select distinct on (p.code, ac.technology) {OFFER_COLUMNS.format(matched=AREA_MATCH)}
from street s
join coverage_area ac on st_intersects(ac.geom_2d, s.geom::geometry)
join provider p on p.id = ac.provider_id
left join provider ip on ip.id = ac.infra_provider_id
left join speed_band sb on sb.id = ac.speed_band_id
where s.id = %s
order by p.code, ac.technology, sb.min_mbps desc nulls last
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
    offers: list[Offer]


class StreetDetail(BaseModel):
    id: int
    name: str
    municipality: str | None
    highway: str
    ways: int = Field(description="OSM ways merged into this street")
    offers: list[Offer]


def offers(found: list[tuple[Any, ...]]) -> list[Offer]:
    return [
        Offer(
            provider=row[0], provider_name=row[1], technology=row[2], family=row[3],
            matched_by=row[4], available_from=row[5], infra_provider=row[6],
            speed=None if row[7] is None else Speed(
                band=row[7], min_mbps=row[8], max_mbps=row[9], label=row[10]
            ),
        )
        for row in found
    ]


def one(sql: str, identifier: int, missing: str) -> tuple[Any, ...]:
    found = rows(sql, (identifier,))
    if not found:
        raise HTTPException(status_code=404, detail=missing)
    return found[0]


@app.get("/addresses/{address_id}", response_model=AddressDetail, tags=["address"])
def address(address_id: int) -> AddressDetail:
    """Everything filed at one address, with each offer's evidence and freshness."""
    row = one(ADDRESS_DETAIL, address_id, "no such address")
    return AddressDetail(
        id=row[0], street=row[1], street_no=row[2], locality=row[3], municipality=row[4],
        postcode=row[5], premises=row[6], connected=row[7], vhcn=row[8],
        lon=row[9], lat=row[10], offers=offers(rows(ADDRESS_OFFERS, (address_id,))),
    )


@app.get("/streets/{street_id}", response_model=StreetDetail, tags=["street"])
def street(street_id: int) -> StreetDetail:
    """A street where no address is filed: coverage comes from the cabinets it crosses."""
    row = one(STREET_DETAIL, street_id, "no such street")
    return StreetDetail(
        id=row[0], name=row[1], municipality=row[2], highway=row[3], ways=row[4],
        offers=offers(rows(STREET_OFFERS, (street_id,))),
    )


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


# The three that sell to households and can be asked. The rest are read from the register
# and from what they publish, because there is nothing of theirs to ask.
RETAIL = ["OTE", "VODAFONE", "NOVA"]


class Cost(BaseModel):
    """A monthly cost in its parts, so a card can say why a cheap headline is not cheap."""

    total: Decimal
    recurring: Decimal
    upfront: Decimal = Field(description="setup and equipment, spread over the window")


class Buyable(BaseModel):
    provider: str
    plan: str
    technology: str
    family: str
    expected_mbps: Decimal | None = Field(description="null when nothing here can say")
    data_cap_gb: int | None = Field(description="null is unlimited, not unknown")
    cost: Cost | None = Field(description="null when a part of it was never published")
    basis: str = Field(description="quoted, measured, filed or advertised")
    tests: int = Field(description="measurements behind it, zero when it rests on none")
    confidence: float = Field(description="evidence from tests alone; a quote has none")
    enough: bool = Field(description="covers an ordinary household, on speed and allowance")
    why: str


class Options(BaseModel):
    address_id: int
    need_mbps: Decimal = Field(description="the bar used, which the caller may move")
    known: dict[str, str] = Field(description="per operator: how the answer was arrived at")
    options: list[Buyable]


# Blending a lump sum across two years is an exact division and rarely lands on a cent.
# The arithmetic stays exact and the answer is rounded once, here, where it is read.
CENTS = Decimal("0.01")


def cents(amount: object) -> Decimal:
    return Decimal(str(amount)).quantize(CENTS, rounding=ROUND_HALF_UP)


def priced(total: object, recurring: object, upfront: object) -> Cost:
    return Cost(total=cents(total), recurring=cents(recurring), upfront=cents(upfront))


@app.get("/addresses/{address_id}/options", response_model=Options, tags=["address"])
def address_options(
    address_id: int,
    need_mbps: Annotated[Decimal, Query(gt=0, le=10000)] = ENOUGH_MBPS,
) -> Options:
    """What can be bought here, best first, from what is already known.

    Nothing is asked of an operator on this path. A page that waits eight seconds for three
    checkers is a page nobody sees the end of, so the stored answer is served at once and
    `known` says, per operator, whether asking would add anything.
    """
    with pool.connection() as conn:
        found = conn.execute("select 1 from address where id = %s", (address_id,)).fetchone()
        if found is None:
            raise HTTPException(404, "no such address")
        known = verdicts(conn, address_id, RETAIL, now=datetime.now(UTC))
        ranked = rank(buyable(conn, address_id), need=need_mbps)

    return Options(
        address_id=address_id,
        need_mbps=need_mbps,
        known=known,
        options=[
            Buyable(
                provider=r.option.provider,
                plan=r.option.plan,
                technology=r.option.technology,
                family=r.option.family,
                expected_mbps=r.option.expected_mbps,
                data_cap_gb=r.option.data_cap_gb,
                cost=None if r.option.cost is None else priced(
                    r.option.cost.total, r.option.cost.recurring, r.option.cost.upfront
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


@app.post("/addresses/{address_id}/probe", response_model=list[Probed], tags=["address"])
def address_probe(address_id: int) -> list[Probed]:
    """Ask the operators that are due, and keep what they say.

    The one path here that leaves the building. It is slow by nature, it is a write, and it
    is rate limited at the proxy for the same reasons the report endpoint is.
    """
    with pool.connection() as conn:
        target = target_for(conn, address_id)
        if target is None:
            raise HTTPException(404, "no such address")
        answers = refresh(conn, target, [Cosmote(), Vodafone(), Nova()], datetime.now(UTC))

    return [
        Probed(
            provider=code,
            asked=True,
            reached=answer.probed is not None,
            serviceable=(
                None if answer.probed is None or not answer.probed.conclusive
                else answer.probed.serviceable
            ),
            detail=answer.error,
        )
        for code, answer in sorted(answers.items())
    ]
