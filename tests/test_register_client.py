from __future__ import annotations

import httpx
import pytest

from ingest.register import (
    Dataset,
    RegisterClient,
    RegisterSchemaError,
    check_columns,
    parse_total,
    retry_delay,
)

TOY = Dataset("toy", "toy", "id", frozenset({"id", "v"}))
ROWS = [{"id": n, "v": f"row{n}"} for n in range(1, 8)]


def fake_register(rows: list[dict[str, object]], cap: int) -> httpx.MockTransport:
    # truncates every page to cap without saying so, like the real one
    def handler(request: httpx.Request) -> httpx.Response:
        params = request.url.params
        limit = int(params.get("limit", len(rows)))
        selected = rows
        after = params.get("id")
        if after is not None:
            last = int(str(after).removeprefix("gt."))
            selected = [r for r in selected if int(str(r["id"])) > last]
        if params.get("select") == "id":
            selected = [{"id": r["id"]} for r in selected]

        page = selected[: min(limit, cap)]
        total = str(len(rows)) if request.headers.get("prefer") == "count=exact" else "*"
        return httpx.Response(200, json=page, headers={"content-range": f"0-{max(len(page) - 1, 0)}/{total}"})

    return httpx.MockTransport(handler)


def client_for(transport: httpx.MockTransport) -> RegisterClient:
    return RegisterClient(httpx.Client(transport=transport), base_url="https://register.invalid/api", delay_s=0,
                          sleep=lambda _: None)


def test_parse_total() -> None:
    for header, expected in [
        ("0-0/2673805", 2673805),
        ("0-499/500", 500),
        ("*/*", None),
        ("0-0/*", None),
        (None, None),
        ("nonsense", None),
    ]:
        assert parse_total(header) == expected


def test_retry_delay() -> None:
    assert retry_delay(httpx.Response(429, headers={"retry-after": "12"}), 0) == 12.0
    # an HTTP date, so back off instead
    r = httpx.Response(429, headers={"retry-after": "Wed, 21 Oct 2026 07:28:00 GMT"})
    assert retry_delay(r, 3) == 8.0
    r = httpx.Response(503)
    assert [retry_delay(r, n) for n in range(4)] == [1.0, 2.0, 4.0, 8.0]


def test_check_columns() -> None:
    check_columns(TOY, {"id": 1, "v": "a"})
    with pytest.raises(RegisterSchemaError, match=r"added=\['extra'\]"):
        check_columns(TOY, {"id": 1, "v": "a", "extra": True})
    with pytest.raises(RegisterSchemaError, match=r"removed=\['v'\]"):
        check_columns(TOY, {"id": 1})


def test_cap() -> None:
    client = client_for(fake_register(ROWS, cap=3))
    assert client.count(TOY) == len(ROWS)
    assert client.page_cap(TOY) == 3

    client = client_for(fake_register(ROWS, cap=1000))
    assert client.page_cap(TOY, probe=4) == 4
    # 7 rows for 2000 asked is the whole table
    assert client.page_cap(TOY) == 2000


def test_pages() -> None:
    client = client_for(fake_register(ROWS, cap=3))
    assert [row for page in client.pages(TOY, cap=3) for row in page] == ROWS
    seen = [row for page in client.pages(TOY, cap=3, after="4") for row in page]
    assert [row["id"] for row in seen] == [5, 6, 7]
    assert [len(page) for page in client.pages(TOY, cap=3)] == [3, 3, 1]

    client = client_for(fake_register([{"id": 1, "v": "a", "surprise": 2}], cap=10))
    with pytest.raises(RegisterSchemaError):
        list(client.pages(TOY, cap=10))


def test_retries() -> None:
    attempts: list[int] = []

    def flaky(request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        if len(attempts) < 3:
            return httpx.Response(503)
        return httpx.Response(200, json=[{"id": 1, "v": "a"}])

    assert client_for(httpx.MockTransport(flaky)).rows("toy", {"limit": 1}) == [{"id": 1, "v": "a"}]
    assert len(attempts) == 3

    client = client_for(httpx.MockTransport(lambda _: httpx.Response(503)))
    with pytest.raises(httpx.HTTPError, match="still failing"):
        client.rows("toy", {"limit": 1})

    attempts.clear()

    def missing(request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        return httpx.Response(404)

    with pytest.raises(httpx.HTTPStatusError):
        client_for(httpx.MockTransport(missing)).rows("toy", {"limit": 1})
    assert len(attempts) == 1


def test_where() -> None:
    seen: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(dict(request.url.params))
        return httpx.Response(200, json=[], headers={"content-range": "*/0"})

    filtered = Dataset("toy", "toy", "id", frozenset({"id", "v"}), where={"or": "(a.eq.1)"})
    client = client_for(httpx.MockTransport(handler))
    client.count(filtered)
    client.page_cap(filtered, probe=10)
    list(client.pages(filtered, cap=10))
    assert seen, "no requests were made"
    assert all(params.get("or") == "(a.eq.1)" for params in seen)

    seen.clear()
    client.count(TOY)
    assert all("or" not in params for params in seen)
