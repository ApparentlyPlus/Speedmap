"""Read-only JSON over the register. Computes nothing: it returns stored state, including
the state of not knowing."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Query
from psycopg_pool import ConnectionPool
from pydantic import BaseModel, Field

from db.settings import settings
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

SUMMARY_COLUMNS = "id, street, street_no, locality, postcode, premises"

PREFIX = f"""
select {SUMMARY_COLUMNS}
from address
where search_key like %s
order by premises desc nulls last, search_key
limit %s
"""

# Only for what the prefix missed: a mid-string match costs 10ms against 0.3ms.
FUZZY = f"""
select {SUMMARY_COLUMNS}
from address
where search_key %% %s and not (search_key like %s)
order by similarity(search_key, %s) desc, premises desc nulls last
limit %s
"""


class AddressSummary(BaseModel):
    id: int
    street: str
    street_no: str | None
    locality: str | None
    postcode: str | None
    premises: int | None = Field(description="dwellings passed, null when not filed")
    match: str = Field(description="prefix or fuzzy")


def like_literal(text: str) -> str:
    """Escape the wildcards, so a user typing % searches for a percent sign."""
    for character in ("\\", "%", "_"):
        text = text.replace(character, "\\" + character)
    return text


def summaries(found: list[tuple[Any, ...]], match: str) -> list[AddressSummary]:
    return [
        AddressSummary(
            id=row[0],
            street=row[1],
            street_no=row[2],
            locality=row[3],
            postcode=row[4],
            premises=row[5],
            match=match,
        )
        for row in found
    ]


@app.get("/addresses", response_model=list[AddressSummary], tags=["address"])
def search(
    q: str = Query(min_length=MIN_QUERY, description="street, optionally with a locality"),
    limit: int = Query(8, ge=1, le=MAX_RESULTS),
) -> list[AddressSummary]:
    """Type-ahead over the address index, folded the same way the index was built."""
    folded = street_key(q)
    pattern = like_literal(folded) + "%"

    found = summaries(rows(PREFIX, (pattern, limit)), "prefix")
    if len(found) < limit:
        remaining = limit - len(found)
        found += summaries(rows(FUZZY, (folded, pattern, folded, remaining)), "fuzzy")
    return found
