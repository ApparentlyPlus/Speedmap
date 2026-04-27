"""Read-only JSON over the register. Computes nothing: it returns stored state, including
the state of not knowing."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from psycopg_pool import ConnectionPool
from pydantic import BaseModel, Field

from db.settings import settings
from normalise.greeklish import from_latin, is_greeklish
from normalise.text import street_key

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
