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
from normalise.greeklish import from_greek
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


# street, street_fold, street_no, locality, search_key, premises
SAMPLE = [
    ("Αχαρνών", "ΑΧΑΡΝΩΝ", "128", "ΑΘΗΝΑ", "ΑΧΑΡΝΩΝ ΑΘΗΝΑ", 30),
    ("Αχαρνών", "ΑΧΑΡΝΩΝ", "12", "ΑΘΗΝΑ", "ΑΧΑΡΝΩΝ ΑΘΗΝΑ", 4),
    ("Λεωφόρος Αλεξάνδρας", "ΑΛΕΞΑΝΔΡΑΣ", "5", "ΑΘΗΝΑ", "ΑΛΕΞΑΝΔΡΑΣ ΑΘΗΝΑ", 12),
    ("Αγίου Ιωάννου", "ΑΓΙΟΥ ΙΩΑΝΝΟΥ", "7", "ΗΛΙΟΥΠΟΛΗ", "ΑΓΙΟΥ ΙΩΑΝΝΟΥ ΗΛΙΟΥΠΟΛΗ", 7),
    ("100% Οδός", "100% ΟΔΟΣ", "1", "ΑΘΗΝΑ", "100% ΟΔΟΣ ΑΘΗΝΑ", 1),
]


@pytest.fixture
def seeded_address(db: psycopg.Connection[TupleRow]) -> Iterator[None]:
    for street, fold, number, locality, key, premises in SAMPLE:
        db.execute(
            "insert into address (street, street_fold, street_no, locality, search_key, "
            "latin_key, premises, geom) values "
            "(%s, %s, %s, %s, %s, %s, %s, 'SRID=4326;POINT(23.7 37.9)')",
            (street, fold, number, locality, key, from_greek(key), premises),
        )
    db.commit()
    yield
    db.execute("truncate address cascade")
    db.commit()


async def found(client: httpx.AsyncClient, q: str, **params: int) -> list[dict[str, object]]:
    response = await client.get("/addresses", params={"q": q, **params})
    assert response.status_code == 200, response.text
    body = response.json()
    assert isinstance(body, list)
    return body


async def test_health_reports_the_database(client: httpx.AsyncClient) -> None:
    body = (await client.get("/health")).json()
    assert body == {"ok": True, "addresses": 0, "offers": 0}


async def test_health_counts_what_is_built(
    client: httpx.AsyncClient, seeded_address: None
) -> None:
    body = (await client.get("/health")).json()
    assert body["addresses"] == len(SAMPLE)


async def test_the_schema_is_served(client: httpx.AsyncClient) -> None:
    """OpenAPI is generated from the models, so it cannot drift from the code."""
    schema = (await client.get("/openapi.json")).json()
    assert schema["info"]["title"] == "speedmap.gr"
    assert "/health" in schema["paths"]


async def test_a_prefix_finds_the_street(
    client: httpx.AsyncClient, seeded_address: None
) -> None:
    hits = await found(client, "ΑΧΑΡΝΩΝ")
    assert {h["street_no"] for h in hits} == {"128", "12"}
    assert all(h["match"] == "prefix" for h in hits)


async def test_bigger_buildings_come_first(
    client: httpx.AsyncClient, seeded_address: None
) -> None:
    """Ranked by dwellings passed, so the block of flats beats the single house."""
    hits = await found(client, "ΑΧΑΡΝΩΝ")
    assert [h["street_no"] for h in hits] == ["128", "12"]


async def test_the_query_is_folded_like_the_index(
    client: httpx.AsyncClient, seeded_address: None
) -> None:
    """Typing lowercase and accented must find what was stored uppercase and stripped."""
    hits = await found(client, "αχαρνών αθηνα")
    assert [h["street_no"] for h in hits] == ["128", "12"]


async def test_a_type_word_in_the_query_is_ignored(
    client: httpx.AsyncClient, seeded_address: None
) -> None:
    """The index dropped ΛΕΩΦΟΡΟΣ, so the query must drop it too or nothing matches."""
    hits = await found(client, "Λεωφ Αλεξανδρας")
    assert [h["street"] for h in hits] == ["Λεωφόρος Αλεξάνδρας"]


async def test_a_mid_string_match_falls_back_to_fuzzy(
    client: httpx.AsyncClient, seeded_address: None
) -> None:
    """ΙΩΑΝΝΟΥ is not a prefix of ΑΓΙΟΥ ΙΩΑΝΝΟΥ, so only the trigram index can find it."""
    hits = await found(client, "ΙΩΑΝΝΟΥ")
    assert [h["match"] for h in hits] == ["fuzzy"]
    assert hits[0]["street"] == "Αγίου Ιωάννου"


async def test_a_wildcard_is_searched_for_literally(
    client: httpx.AsyncClient, seeded_address: None
) -> None:
    """Otherwise '%' matches every address in the country."""
    hits = await found(client, "100%")
    assert [h["street"] for h in hits] == ["100% Οδός"]


async def test_an_underscore_is_not_a_wildcard(
    client: httpx.AsyncClient, seeded_address: None
) -> None:
    assert await found(client, "1_0") == []


async def test_nothing_found_is_an_empty_list(
    client: httpx.AsyncClient, seeded_address: None
) -> None:
    """Not an error, and not a guess at what was meant."""
    assert await found(client, "ΞΞΞΞΞΞ") == []


async def test_one_character_is_rejected(client: httpx.AsyncClient) -> None:
    """Autocomplete opens on the second keystroke; a single letter matches too much."""
    assert (await client.get("/addresses", params={"q": "Α"})).status_code == 422


async def test_the_limit_is_capped(client: httpx.AsyncClient, seeded_address: None) -> None:
    assert (await client.get("/addresses", params={"q": "ΑΧ", "limit": 999})).status_code == 422


async def test_the_limit_is_respected(
    client: httpx.AsyncClient, seeded_address: None
) -> None:
    assert len(await found(client, "ΑΧΑΡΝΩΝ", limit=1)) == 1
