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

# Streets exist where the register files no address at all, as in Lagkadas.
STREETS = [("Αχιλλέα Τζελίλη", "ΑΧΙΛΛΕΑ ΤΖΕΛΙΛΗ"), ("Πάροδος Τζελίλη", "ΠΑΡΟΔΟΣ ΤΖΕΛΙΛΗ")]


@pytest.fixture
def seeded_address(db: psycopg.Connection[TupleRow]) -> Iterator[None]:
    for street, fold, number, locality, key, premises in SAMPLE:
        db.execute(
            "insert into address (street, street_fold, street_no, locality, search_key, "
            "latin_key, premises, geom) values "
            "(%s, %s, %s, %s, %s, %s, %s, 'SRID=4326;POINT(23.7 37.9)')",
            (street, fold, number, locality, key, from_greek(key), premises),
        )
    for name, fold in STREETS:
        db.execute(
            "insert into street (name, name_fold, latin_key, sort_key, highway, ways, geom) "
            "values (%s, %s, %s, %s, 'residential', 1, "
            "'SRID=4326;MULTILINESTRING((23.0 40.7, 23.01 40.71))')",
            (name, fold, from_greek(fold), " ".join(sorted(fold.split()))),
        )
    db.commit()
    yield
    db.execute("truncate address, street cascade")
    db.commit()


async def found(client: httpx.AsyncClient, q: str, **params: int) -> list[dict[str, object]]:
    response = await client.get("/search", params={"q": q, **params})
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




async def test_a_prefix_finds_the_address(
    client: httpx.AsyncClient, seeded_address: None
) -> None:
    hits = await found(client, "ΑΧΑΡΝΩΝ")
    assert {h["street_no"] for h in hits} == {"128", "12"}
    assert all(h["match"] == "prefix" and h["kind"] == "address" for h in hits)


async def test_bigger_buildings_come_first(
    client: httpx.AsyncClient, seeded_address: None
) -> None:
    """Within a tier every row matched equally well, so rank by dwellings passed."""
    hits = await found(client, "ΑΧΑΡΝΩΝ")
    assert [h["street_no"] for h in hits] == ["128", "12"]


async def test_the_query_is_folded_like_the_index(
    client: httpx.AsyncClient, seeded_address: None
) -> None:
    hits = await found(client, "αχαρνών αθηνα")
    assert [h["street_no"] for h in hits] == ["128", "12"]


async def test_a_type_word_in_the_query_is_ignored(
    client: httpx.AsyncClient, seeded_address: None
) -> None:
    hits = await found(client, "Λεωφ Αλεξανδρας")
    assert [h["name"] for h in hits] == ["Λεωφόρος Αλεξάνδρας"]


# Greeklish


async def test_greeklish_finds_the_same_address(
    client: httpx.AsyncClient, seeded_address: None
) -> None:
    greek = await found(client, "ΑΧΑΡΝΩΝ")
    latin = await found(client, "axarnon")
    assert [h["id"] for h in latin] == [h["id"] for h in greek]


async def test_greeklish_reaches_a_street_with_no_addresses(
    client: httpx.AsyncClient, seeded_address: None
) -> None:
    """The whole point: 168 municipalities have streets and no addresses at all."""
    hits = await found(client, "tzelili")
    assert hits[0]["kind"] == "street"
    assert hits[0]["name"] == "Αχιλλέα Τζελίλη"


async def test_a_word_in_the_middle_is_found(
    client: httpx.AsyncClient, seeded_address: None
) -> None:
    """ΤΖΕΛΙΛΗ is not a prefix of ΑΧΙΛΛΕΑ ΤΖΕΛΙΛΗ, so the prefix tier cannot see it."""
    hits = await found(client, "Τζελίλη")
    assert [h["match"] for h in hits[:2]] == ["word", "word"]


async def test_addresses_are_offered_before_streets(
    client: httpx.AsyncClient, seeded_address: None
) -> None:
    """An address is actionable; a street is where we fall back to."""
    hits = await found(client, "ΑΧΑΡΝΩΝ")
    kinds = [h["kind"] for h in hits]
    assert kinds == sorted(kinds, key=lambda k: k != "address")


# guards


async def test_a_wildcard_is_searched_for_literally(
    client: httpx.AsyncClient, seeded_address: None
) -> None:
    hits = await found(client, "100%")
    assert [h["name"] for h in hits] == ["100% Οδός"]


async def test_an_underscore_is_not_a_wildcard(
    client: httpx.AsyncClient, seeded_address: None
) -> None:
    assert await found(client, "1_0") == []


async def test_nothing_found_is_an_empty_list(
    client: httpx.AsyncClient, seeded_address: None
) -> None:
    assert await found(client, "ΞΞΞΞΞΞ") == []


async def test_one_character_is_rejected(client: httpx.AsyncClient) -> None:
    assert (await client.get("/search", params={"q": "Α"})).status_code == 422


async def test_the_limit_is_capped(client: httpx.AsyncClient, seeded_address: None) -> None:
    assert (await client.get("/search", params={"q": "ΑΧ", "limit": 999})).status_code == 422


async def test_the_limit_is_respected(
    client: httpx.AsyncClient, seeded_address: None
) -> None:
    assert len(await found(client, "ΑΧΑΡΝΩΝ", limit=1)) == 1


@pytest.fixture
def seeded_offer(db: psycopg.Connection[TupleRow], seeded_address: None) -> Iterator[int]:
    """One address with two offers: a fibre one with a band, a copper one without."""
    row = db.execute("select id from address order by id limit 1").fetchone()
    assert row is not None
    address_id = int(row[0])
    db.execute(
        "insert into address_coverage (address_id, provider_id, technology, "
        "infra_provider_id, speed_band_id, family, matched_by) values "
        "(%s, (select id from provider where code='NOVA'), 'FTTH', "
        "(select id from provider where code='FIBERGRID'), 8, 'fibre', 'point')",
        (address_id,),
    )
    db.execute(
        "insert into address_coverage (address_id, provider_id, technology, "
        "speed_band_id, family, matched_by) values "
        "(%s, (select id from provider where code='OTE'), 'ADSL', null, 'copper', 'area')",
        (address_id,),
    )
    db.commit()
    yield address_id
    db.execute("truncate address_coverage")
    db.commit()


async def test_an_address_carries_its_offers(
    client: httpx.AsyncClient, seeded_offer: int
) -> None:
    body = (await client.get(f"/addresses/{seeded_offer}")).json()
    assert body["street"] == "Αχαρνών"
    assert {o["provider"] for o in body["offers"]} == {"NOVA", "OTE"}


async def test_an_offer_with_no_filed_speed_says_so(
    client: httpx.AsyncClient, seeded_offer: int
) -> None:
    """73.3% of filed services carry no band. Null must survive to the client, not become 0."""
    body = (await client.get(f"/addresses/{seeded_offer}")).json()
    copper = next(o for o in body["offers"] if o["provider"] == "OTE")
    assert copper["speed"] is None


async def test_a_band_is_reported_as_a_range(
    client: httpx.AsyncClient, seeded_offer: int
) -> None:
    """The register files a range, never a number, and the open end stays open."""
    body = (await client.get(f"/addresses/{seeded_offer}")).json()
    fibre = next(o for o in body["offers"] if o["provider"] == "NOVA")
    assert fibre["speed"] == {
        "band": 8,
        "min_mbps": 1000.0,
        "max_mbps": None,
        "label": ">= 1000 Mbps",
    }


async def test_the_builder_is_reported_separately(
    client: httpx.AsyncClient, seeded_offer: int
) -> None:
    """Nova sells over FIBERGRID's fibre; collapsing them hides who owns the network."""
    body = (await client.get(f"/addresses/{seeded_offer}")).json()
    fibre = next(o for o in body["offers"] if o["provider"] == "NOVA")
    assert fibre["infra_provider"] == "FIBERGRID"


async def test_how_the_match_was_made_is_reported(
    client: httpx.AsyncClient, seeded_offer: int
) -> None:
    """A filing against this building is stronger evidence than falling inside a cabinet."""
    body = (await client.get(f"/addresses/{seeded_offer}")).json()
    assert {o["provider"]: o["matched_by"] for o in body["offers"]} == {
        "NOVA": "point",
        "OTE": "area",
    }


async def test_an_unknown_address_is_not_found(client: httpx.AsyncClient) -> None:
    assert (await client.get("/addresses/999999999")).status_code == 404


async def test_an_unknown_street_is_not_found(client: httpx.AsyncClient) -> None:
    assert (await client.get("/streets/999999999")).status_code == 404


async def test_a_street_reports_its_merged_ways(
    client: httpx.AsyncClient, seeded_address: None
) -> None:
    hits = await found(client, "tzelili")
    body = (await client.get(f"/streets/{hits[0]['id']}")).json()
    assert body["name"] == "Αχιλλέα Τζελίλη"
    assert body["ways"] == 1
    assert body["offers"] == []


async def test_a_report_is_recorded(client: httpx.AsyncClient) -> None:
    """Everything here is best effort, and best effort only improves if people can say so."""
    response = await client.post("/reports", json={
        "kind": "price", "detail": "Το 1Gbps δεν κοστίζει 60 ευρώ, το πήρα 19,90.",
    })
    assert response.status_code == 201
    assert response.json()["id"] > 0


async def test_a_report_needs_something_to_say(client: httpx.AsyncClient) -> None:
    """A blank report is noise in the queue that someone has to read."""
    response = await client.post("/reports", json={"kind": "price", "detail": "όχι"})
    assert response.status_code == 422


async def test_a_report_about_nothing_we_hold_is_refused(client: httpx.AsyncClient) -> None:
    """An id we do not have is a mistaken report, not a server fault."""
    response = await client.post("/reports", json={
        "kind": "availability", "detail": "This address has fibre, you say it does not.",
        "address_id": 999999999,
    })
    assert response.status_code == 422


async def test_a_report_kind_is_one_of_ours(client: httpx.AsyncClient) -> None:
    response = await client.post("/reports", json={
        "kind": "complaint", "detail": "something is wrong here somewhere",
    })
    assert response.status_code == 422


async def test_a_long_report_is_capped(client: httpx.AsyncClient) -> None:
    """Free text is capped rather than trusted."""
    response = await client.post("/reports", json={"kind": "other", "detail": "x" * 3000})
    assert response.status_code == 422


async def test_options_are_ranked_and_priced(client: httpx.AsyncClient) -> None:
    """The whole engine, over HTTP: what is buyable here, best first."""
    address = await client.get("/search", params={"q": "Αχαρνών"})
    found = [r for r in address.json() if r["kind"] == "address"]
    if not found:
        pytest.skip("the scratch database holds no address to rank")
    response = await client.get(f"/addresses/{found[0]['id']}/options")
    assert response.status_code == 200
    body = response.json()
    assert body["need_mbps"] == "100"
    assert set(body["known"]) == {"OTE", "VODAFONE", "NOVA"}


async def test_options_for_nothing_are_a_404(client: httpx.AsyncClient) -> None:
    response = await client.get("/addresses/999999999/options")
    assert response.status_code == 404


async def test_the_bar_can_be_moved_by_the_caller(client: httpx.AsyncClient) -> None:
    """Someone working from home wants the gigabit the household does not."""
    address = await client.get("/search", params={"q": "Αχαρνών"})
    found = [r for r in address.json() if r["kind"] == "address"]
    if not found:
        pytest.skip("the scratch database holds no address to rank")
    response = await client.get(
        f"/addresses/{found[0]['id']}/options", params={"need_mbps": "500"}
    )
    assert response.json()["need_mbps"] == "500"


async def test_a_bar_of_nothing_is_refused(client: httpx.AsyncClient) -> None:
    address = await client.get("/search", params={"q": "Αχαρνών"})
    found = [r for r in address.json() if r["kind"] == "address"]
    if not found:
        pytest.skip("the scratch database holds no address to rank")
    response = await client.get(
        f"/addresses/{found[0]['id']}/options", params={"need_mbps": "0"}
    )
    assert response.status_code == 422


async def test_a_result_carries_its_best_known_speed(client: httpx.AsyncClient) -> None:
    """The dot beside a suggestion teaches the ramp before anyone reaches the map."""
    response = await client.get("/search", params={"q": "Αχαρνών"})
    found = response.json()
    if not found:
        pytest.skip("the scratch database holds nothing to search")
    assert "best_mbps" in found[0]


async def test_an_address_with_no_street_name_is_not_suggested(
    client: httpx.AsyncClient, db: psycopg.Connection[TupleRow]
) -> None:
    """The register files a bare dash where it holds no name. Such a row reads as '- -' and
    tells the reader nothing they can act on, so it stays in the index and out of search."""
    db.execute(
        "insert into address (street, street_fold, street_no, geom, search_key, latin_key) "
        "values ('-', '-', '-', st_setsrid(st_point(23.7, 37.9), 4326), "
        "'ΑΧΑΡΝΩΝ ΔΑΣΗ', 'ACHARNON DASI')"
    )
    db.commit()
    response = await client.get("/search", params={"q": "ΑΧΑΡΝΩΝ ΔΑΣΗ"})
    assert all(r["name"] != "-" for r in response.json())
