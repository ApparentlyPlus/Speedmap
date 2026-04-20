"""Read-only JSON over the register. Computes nothing: it returns stored state, including
the state of not knowing."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from psycopg_pool import ConnectionPool
from pydantic import BaseModel, Field

from db.settings import settings

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
