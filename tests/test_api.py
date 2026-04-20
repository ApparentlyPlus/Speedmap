"""The read-only API, driven against the scratch database through ASGI."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

import httpx
import psycopg
import pytest
import pytest_asyncio
from psycopg.rows import TupleRow
from psycopg_pool import ConnectionPool

from api import main
from tests.conftest import TEST_DSN


@pytest_asyncio.fixture
async def client(db: psycopg.Connection[TupleRow]) -> AsyncIterator[httpx.AsyncClient]:
    """The app with its pool pointed at the test database, driven without a network."""
    original = main.pool
    main.pool = ConnectionPool(TEST_DSN, min_size=1, max_size=2, open=True)
    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    main.pool.close()
    main.pool = original


@pytest.fixture
def seeded_address(db: psycopg.Connection[TupleRow]) -> Iterator[None]:
    db.execute(
        "insert into address (street, street_fold, geom, search_key) "
        "values ('ΑΧΑΡΝΩΝ', 'ΑΧΑΡΝΩΝ', 'SRID=4326;POINT(23.7 37.9)', 'ΑΧΑΡΝΩΝ')"
    )
    db.commit()
    yield
    db.execute("truncate address cascade")
    db.commit()


async def test_health_reports_the_database(client: httpx.AsyncClient) -> None:
    body = (await client.get("/health")).json()
    assert body == {"ok": True, "addresses": 0, "offers": 0}


async def test_health_counts_what_is_built(
    client: httpx.AsyncClient, seeded_address: None
) -> None:
    body = (await client.get("/health")).json()
    assert body["addresses"] == 1


async def test_the_schema_is_served(client: httpx.AsyncClient) -> None:
    """OpenAPI is generated from the models, so it cannot drift from the code."""
    schema = (await client.get("/openapi.json")).json()
    assert schema["info"]["title"] == "speedmap.gr"
    assert "/health" in schema["paths"]
