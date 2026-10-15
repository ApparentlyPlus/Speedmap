from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

import httpx
import psycopg
import pytest
import pytest_asyncio
from psycopg.rows import TupleRow
from psycopg_pool import ConnectionPool

from api import main
from normalise.build import STEPS, sql_step
from normalise.greeklish import from_greek
from tests.conftest import TEST_DSN


@pytest_asyncio.fixture
async def client(db: psycopg.Connection[TupleRow]) -> AsyncIterator[httpx.AsyncClient]:
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
    # surname first here, forename first a suburb away
    ("Συμεωνίδη Αλεξάνδρου", "ΣΥΜΕΩΝΙΔΗ ΑΛΕΞΑΝΔΡΟΥ", "8", "ΘΕΣΣΑΛΟΝΙΚΗ",
     "ΣΥΜΕΩΝΙΔΗ ΑΛΕΞΑΝΔΡΟΥ ΘΕΣΣΑΛΟΝΙΚΗ", 9),
]

# no address filed on them at all, as in Lagkadas
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


def _built(db: psycopg.Connection[TupleRow], *steps: str) -> None:
    for name in steps:
        sql_step(STEPS / f"{name}.sql").run(db)
    db.commit()


async def _found(client: httpx.AsyncClient, q: str, **params: str | int) -> list[dict[str, object]]:
    response = await client.get("/search", params={"q": q, **params})
    assert response.status_code == 200, response.text
    body = response.json()
    assert isinstance(body, list)
    return body


async def _address_id(client: httpx.AsyncClient) -> int:
    hits = [r for r in (await client.get("/search", params={"q": "Αχαρνών"})).json() if r["kind"] == "address"]
    if not hits:
        pytest.skip("the scratch database holds no address")
    return int(hits[0]["id"])


async def test_health(client: httpx.AsyncClient) -> None:
    assert (await client.get("/health")).json() == {"ok": True, "addresses": 0, "offers": 0}
    schema = (await client.get("/openapi.json")).json()
    assert schema["info"]["title"] == "speedmap.gr"
    assert "/health" in schema["paths"]


async def test_health_seeded(client: httpx.AsyncClient, seeded_address: None) -> None:
    assert (await client.get("/health")).json()["addresses"] == len(SAMPLE)


async def test_search(client: httpx.AsyncClient, seeded_address: None) -> None:
    hits = await _found(client, "ΑΧΑΡΝΩΝ")
    assert {h["street_no"] for h in hits} == {"128", "12"}
    assert all(h["match"] == "prefix" and h["kind"] == "address" for h in hits)
    # same match, so the bigger building first
    assert [h["street_no"] for h in hits] == ["128", "12"]
    kinds = [h["kind"] for h in hits]
    assert kinds == sorted(kinds, key=lambda k: k != "address")

    assert [h["street_no"] for h in await _found(client, "αχαρνών αθηνα")] == ["128", "12"]
    assert [h["name"] for h in await _found(client, "Λεωφ Αλεξανδρας")] == ["Λεωφόρος Αλεξάνδρας"]

    latin = await _found(client, "axarnon")
    assert [h["id"] for h in latin] == [h["id"] for h in hits]
    # 168 municipalities have streets and no addresses
    hits = await _found(client, "tzelili")
    assert hits[0]["kind"] == "street"
    assert hits[0]["name"] == "Αχιλλέα Τζελίλη"
    # not a prefix of ΑΧΙΛΛΕΑ ΤΖΕΛΙΛΗ, only the word tier gets it
    hits = await _found(client, "Τζελίλη")
    assert [h["match"] for h in hits[:2]] == ["word", "word"]

    hits = await _found(client, "Αλεξάνδρου Συμεωνίδη 8")
    assert hits[0]["name"] == "Συμεωνίδη Αλεξάνδρου"
    assert hits[0]["street_no"] == "8"


async def test_search_numbers(client: httpx.AsyncClient, seeded_address: None) -> None:
    # 128 is bigger, 12 was asked for
    hits = await _found(client, "ΑΧΑΡΝΩΝ 12")
    assert hits[0]["street_no"] == "12"
    assert [h["kind"] for h in hits if h["kind"] == "proposed"] == []
    # the number orders, it doesn't filter
    hits = await _found(client, "ΑΧΑΡΝΩΝ 4000")
    assert [h["street_no"] for h in hits if h["kind"] == "address"] == ["128", "12"]

    assert [h["name"] for h in await _found(client, "100%")] == ["100% Οδός"]

    hits = await _found(client, "Τζελίλη 40")
    assert hits[0]["kind"] == "proposed"
    assert hits[0]["name"] == "Αχιλλέα Τζελίλη"
    assert hits[0]["street_no"] == "40"
    assert hits[0]["street_id"] is not None
    offered = {h["id"] for h in hits if h["kind"] == "proposed"}
    assert not [h for h in hits if h["kind"] == "street" and h["id"] in offered]


async def test_search_guards(client: httpx.AsyncClient, seeded_address: None) -> None:
    hits = await _found(client, "100%")
    assert [h["name"] for h in hits] == ["100% Οδός"]
    assert await _found(client, "1_0") == []
    assert await _found(client, "ΞΞΞΞΞΞ") == []
    assert (await client.get("/search", params={"q": "Α"})).status_code == 422
    assert (await client.get("/search", params={"q": "ΑΧ", "limit": 999})).status_code == 422
    assert len(await _found(client, "ΑΧΑΡΝΩΝ", limit=1)) == 1


async def test_ask_for(client: httpx.AsyncClient, seeded_address: None) -> None:
    street = (await _found(client, "Τζελίλη 40"))[0]["id"]
    made = await client.post(f"/streets/{street}/addresses", json={"street_no": "40"})
    assert made.status_code == 201, made.text
    body = made.json()
    assert body["kind"] == "address"
    assert body["street_no"] == "40"
    assert body["name"] == "Αχιλλέα Τζελίλη"

    again = await client.post(f"/streets/{street}/addresses", json={"street_no": "40"})
    assert made.json()["id"] == again.json()["id"]

    hits = await _found(client, "Τζελίλη 40")
    assert hits[0]["kind"] == "address"
    assert hits[0]["street_no"] == "40"

    assert (await client.post("/streets/999999/addresses", json={"street_no": "40"})).status_code == 404
    made = await client.post(f"/streets/{street}/addresses", json={"street_no": ""})
    assert made.status_code == 422
    # all spaces used to make a door with no number
    made = await client.post(f"/streets/{street}/addresses", json={"street_no": "   "})
    assert made.status_code == 422


async def test_ask_for_neighbour(client: httpx.AsyncClient, db: psycopg.Connection[TupleRow],
                                 seeded_address: None) -> None:
    # the midpoint put Τζελίλη 40 half a km and one Ookla tile away from number 1
    db.execute(
        "insert into address (street, street_fold, street_no, search_key, latin_key, geom) "
        "values ('Αχιλλέα Τζελίλη', 'ΑΧΙΛΛΕΑ ΤΖΕΛΙΛΗ', '1', 'ΑΧΙΛΛΕΑ ΤΖΕΛΙΛΗ', "
        "'ACHILLEA TZELILI', 'SRID=4326;POINT(23.5 40.9)')"
    )
    db.commit()
    street = (await _found(client, "Τζελίλη 40"))[0]["id"]
    made = await client.post(f"/streets/{street}/addresses", json={"street_no": "40"})
    apart = db.execute(
        "select st_distance(a.geom, b.geom) from address a, address b "
        "where a.id = %s and b.street_fold = 'ΑΧΙΛΛΕΑ ΤΖΕΛΙΛΗ' and b.street_no = '1'",
        (made.json()["id"],),
    ).fetchone()
    assert apart is not None
    assert float(apart[0]) == 0.0


async def test_ask_for_midpoint(client: httpx.AsyncClient, db: psycopg.Connection[TupleRow],
                                seeded_address: None) -> None:
    street = (await _found(client, "Τζελίλη 40"))[0]["id"]
    made = await client.post(f"/streets/{street}/addresses", json={"street_no": "40"})
    assert made.status_code == 201
    on_line = db.execute(
        "select st_dwithin(a.geom, s.geom, 1) from address a, street s where a.id = %s and s.id = %s",
        (made.json()["id"], street),
    ).fetchone()
    assert on_line is not None
    assert on_line[0] is True


@pytest.fixture
def seeded_offer(db: psycopg.Connection[TupleRow], seeded_address: None) -> Iterator[int]:
    # fiber with a band, copper without
    row = db.execute("select id from address order by id limit 1").fetchone()
    assert row is not None
    address_id = int(row[0])
    db.execute(
        "insert into address_coverage (address_id, provider_id, technology, "
        "infra_provider_id, speed_band_id, family, matched_by) values "
        "(%s, (select id from provider where code='NOVA'), 'FTTH', "
        "(select id from provider where code='FIBERGRID'), 8, 'fiber', 'point')",
        (address_id,),
    )
    db.execute(
        "insert into address_coverage (address_id, provider_id, technology, "
        "speed_band_id, family, matched_by) values "
        "(%s, (select id from provider where code='TELEKOM'), 'ADSL', null, 'copper', 'area')",
        (address_id,),
    )
    db.commit()
    yield address_id
    db.execute("truncate address_coverage")
    db.commit()


async def test_address(client: httpx.AsyncClient, seeded_offer: int) -> None:
    body = (await client.get(f"/addresses/{seeded_offer}")).json()
    assert body["street"] == "Αχαρνών"
    assert {o["provider"] for o in body["offers"]} == {"NOVA", "TELEKOM"}

    copper = next(o for o in body["offers"] if o["provider"] == "TELEKOM")
    assert copper["speed"] is None  # null, never 0
    fiber = next(o for o in body["offers"] if o["provider"] == "NOVA")
    assert fiber["speed"] == {"band": 8, "min_mbps": 1000.0, "max_mbps": None, "label": ">= 1000 Mbps"}
    assert fiber["infra_provider"] == "FIBERGRID"
    assert {o["provider"]: o["matched_by"] for o in body["offers"]} == {"NOVA": "point", "TELEKOM": "area"}


async def test_not_found(client: httpx.AsyncClient) -> None:
    assert (await client.get("/addresses/999999999")).status_code == 404
    assert (await client.get("/streets/999999999")).status_code == 404
    assert (await client.get("/addresses/999999999/options")).status_code == 404


async def test_street(client: httpx.AsyncClient, seeded_address: None) -> None:
    hits = await _found(client, "tzelili")
    body = (await client.get(f"/streets/{hits[0]['id']}")).json()
    assert body["name"] == "Αχιλλέα Τζελίλη"
    assert body["ways"] == 1
    assert body["offers"] == []


async def test_reports(client: httpx.AsyncClient) -> None:
    r = await client.post("/reports", json={"kind": "price", "detail": "Το 1Gbps δεν κοστίζει 60 ευρώ, το πήρα 19,90."})
    assert r.status_code == 201
    assert r.json()["id"] > 0

    r = await client.post("/reports", json={"kind": "price", "detail": "όχι"})
    assert r.status_code == 422
    # an unknown id is a bad report, not a 500
    r = await client.post("/reports", json={
        "kind": "availability", "detail": "This address has fiber, you say it does not.", "address_id": 999999999,
    })
    assert r.status_code == 422
    r = await client.post("/reports", json={"kind": "complaint", "detail": "something is wrong here somewhere"})
    assert r.status_code == 422
    r = await client.post("/reports", json={"kind": "other", "detail": "x" * 3000})
    assert r.status_code == 422


async def test_options(client: httpx.AsyncClient) -> None:
    aid = await _address_id(client)
    r = await client.get(f"/addresses/{aid}/options")
    assert r.status_code == 200
    body = r.json()
    assert body["need_mbps"] == "100"
    assert set(body["known"]) == {"TELEKOM", "VODAFONE", "NOVA"}

    r = await client.get(f"/addresses/{aid}/options", params={"need_mbps": "500"})
    assert r.json()["need_mbps"] == "500"
    r = await client.get(f"/addresses/{aid}/options", params={"need_mbps": "0"})
    assert r.status_code == 422

    r = await client.post(f"/addresses/{aid}/probe", params={"provider": "NOPE"})
    assert r.status_code == 422


async def test_search_best_mbps(client: httpx.AsyncClient) -> None:
    hits = (await client.get("/search", params={"q": "Αχαρνών"})).json()
    if not hits:
        pytest.skip("the scratch database holds nothing to search")
    assert "best_mbps" in hits[0]


async def test_search_nameless(client: httpx.AsyncClient, db: psycopg.Connection[TupleRow]) -> None:
    # the register's "-" for no name stays indexed but never suggested
    db.execute(
        "insert into address (street, street_fold, street_no, geom, search_key, latin_key) "
        "values ('-', '-', '-', st_setsrid(st_point(23.7, 37.9), 4326), 'ΑΧΑΡΝΩΝ ΔΑΣΗ', 'ACHARNON DASI')"
    )
    db.commit()
    r = await client.get("/search", params={"q": "ΑΧΑΡΝΩΝ ΔΑΣΗ"})
    assert all(h["name"] != "-" for h in r.json())


# The panel and the map colour both read street_offer, which 110 writes. Χανιά - Θέρισο once
# drew at a gigabit and opened on "no road here with declared coverage".
async def test_street_built(client: httpx.AsyncClient, db: psycopg.Connection[TupleRow]) -> None:
    db.execute(
        "insert into provider (code, display_name, kind, builds_own_network, register_id) "
        "values ('BUILDER', 'Builder', 'altnet', true, 904) on conflict (code) do nothing"
    )
    row = db.execute(
        "insert into street (name, name_fold, latin_key, sort_key, highway, ways, geom) "
        "values ('ΦΩΣ', 'ΦΩΣ', 'FOS', 'ΦΩΣ', 'residential', 1, "
        "'SRID=4326;MULTILINESTRING((23.0 40.7, 23.01 40.71))') returning id"
    ).fetchone()
    assert row is not None
    street_id = int(row[0])
    # fiber beside the road and no address, so only route three finds it
    db.execute(
        "insert into raw_coverpoint (coverid, infrprov, prempass, address, point) values "
        "('lit-1', 904, 9, '64007,ΦΩΣ, ,Δ. ΤΕΣΤ', st_setsrid(st_point(23.0, 40.7), 4326))"
    )
    db.commit()
    _built(db, "110_street_reach")

    body = (await client.get(f"/streets/{street_id}")).json()
    assert [(o["provider"], o["matched_by"]) for o in body["offers"]] == [("BUILDER", "built")]

    db.execute("truncate street, raw_coverpoint cascade")
    db.execute("delete from provider where code = 'BUILDER'")
    db.commit()


async def test_street_locality(client: httpx.AsyncClient, db: psycopg.Connection[TupleRow]) -> None:
    # 7,320 names repeat within one municipality, the doors' locality tells them apart
    for component, locality in ((0, "ΚΑΤΩ ΤΟΥΜΠΑ"), (1, "ΑΝΩ ΤΟΥΜΠΑ")):
        row = db.execute(
            "insert into street (name, name_fold, latin_key, sort_key, component, "
            "highway, ways, geom) values ('Παπάφη', 'ΠΑΠΑΦΗ', 'PAPAFI', 'ΠΑΠΑΦΗ', %s, "
            "'residential', 1, 'SRID=4326;MULTILINESTRING((23.0 40.7, 23.01 40.71))') returning id",
            (component,),
        ).fetchone()
        assert row is not None
        db.execute(
            "insert into address (street, street_fold, street_no, locality, search_key, "
            "latin_key, geom, street_id) values ('Παπάφη', 'ΠΑΠΑΦΗ', %s, %s, 'ΠΑΠΑΦΗ', "
            "'PAPAFI', 'SRID=4326;POINT(23.0 40.7)', %s)",
            (str(component + 1), locality, int(row[0])),
        )
    db.commit()
    _built(db, "066_street_locality")
    streets = await _found(client, "Παπάφη", kind="street")
    assert sorted(str(h["locality"]) for h in streets) == ["ΑΝΩ ΤΟΥΜΠΑ", "ΚΑΤΩ ΤΟΥΜΠΑ"]
    db.execute("truncate street, address cascade")
    db.commit()

    # 10,645 runs have no doors, borrowing a locality from across the valley is worse than none
    db.execute(
        "insert into street (name, name_fold, latin_key, sort_key, highway, ways, geom) "
        "values ('Ανώνυμος', 'ΑΝΩΝΥΜΟΣ', 'ANONYMOS', 'ΑΝΩΝΥΜΟΣ', 'track', 1, "
        "'SRID=4326;MULTILINESTRING((21.0 37.0, 21.01 37.01))')"
    )
    db.commit()
    streets = await _found(client, "Ανώνυμος", kind="street")
    assert [h["locality"] for h in streets] == [None]
    db.execute("truncate street cascade")
    db.commit()
