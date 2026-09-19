"""The register client against a fake register: paging, the silent cap, and drift."""

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
    """A register that silently truncates every page to `cap` rows."""

    def handler(request: httpx.Request) -> httpx.Response:
        params = request.url.params
        limit = int(params.get("limit", len(rows)))
        selected = rows
        after = params.get("id")
        if after is not None:
            cursor = int(str(after).removeprefix("gt."))
            selected = [r for r in selected if int(str(r["id"])) > cursor]
        if params.get("select") == "id":
            selected = [{"id": r["id"]} for r in selected]

        page = selected[: min(limit, cap)]
        # PostgREST only counts when asked.
        counted = request.headers.get("prefer") == "count=exact"
        total = str(len(rows)) if counted else "*"
        return httpx.Response(
            200,
            json=page,
            headers={"content-range": f"0-{max(len(page) - 1, 0)}/{total}"},
        )

    return httpx.MockTransport(handler)


def client_for(transport: httpx.MockTransport) -> RegisterClient:
    return RegisterClient(
        httpx.Client(transport=transport),
        base_url="https://register.invalid/api",
        delay_s=0,
        sleep=lambda _seconds: None,
    )


# parse_total.


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("0-0/2673805", 2673805),
        ("0-499/500", 500),
        ("*/*", None),
        ("0-0/*", None),
        (None, None),
        ("nonsense", None),
    ],
)
def test_parse_total(header: str | None, expected: int | None) -> None:
    assert parse_total(header) == expected


# retry_delay.


def test_retry_after_seconds_is_honoured() -> None:
    response = httpx.Response(429, headers={"retry-after": "12"})
    assert retry_delay(response, 0) == 12.0


def test_retry_after_date_falls_back_to_backoff() -> None:
    """An HTTP-date Retry-After is not a number, so back off rather than guess."""
    response = httpx.Response(429, headers={"retry-after": "Wed, 21 Oct 2026 07:28:00 GMT"})
    assert retry_delay(response, 3) == 8.0


def test_backoff_grows_without_a_header() -> None:
    response = httpx.Response(503)
    assert [retry_delay(response, n) for n in range(4)] == [1.0, 2.0, 4.0, 8.0]


# check_columns.


def test_unchanged_columns_pass() -> None:
    check_columns(TOY, {"id": 1, "v": "a"})


def test_added_column_is_drift() -> None:
    with pytest.raises(RegisterSchemaError, match=r"added=\['extra'\]"):
        check_columns(TOY, {"id": 1, "v": "a", "extra": True})


def test_removed_column_is_drift() -> None:
    with pytest.raises(RegisterSchemaError, match=r"removed=\['v'\]"):
        check_columns(TOY, {"id": 1})


# the silent cap.


def test_count_asks_postgrest_to_count() -> None:
    """Without Prefer: count=exact the header carries '*' and the total is lost."""
    client = client_for(fake_register(ROWS, cap=3))
    assert client.count(TOY) == len(ROWS)


def test_cap_is_measured_not_trusted() -> None:
    """Asking for 2000 and getting 3 means the cap is 3, even though nothing said so."""
    client = client_for(fake_register(ROWS, cap=3))
    assert client.page_cap(TOY) == 3


def test_no_cap_below_the_probe_reports_the_probe() -> None:
    client = client_for(fake_register(ROWS, cap=1000))
    assert client.page_cap(TOY, probe=4) == 4


def test_table_shorter_than_the_probe_is_not_a_cap() -> None:
    """7 rows returned for a request of 2000 is the whole table, not a limit."""
    client = client_for(fake_register(ROWS, cap=1000))
    assert client.page_cap(TOY) == 2000


# paging.


def test_paging_returns_every_row_exactly_once() -> None:
    client = client_for(fake_register(ROWS, cap=3))
    seen = [row for page in client.pages(TOY, cap=3) for row in page]
    assert seen == ROWS


def test_paging_resumes_after_a_key() -> None:
    client = client_for(fake_register(ROWS, cap=3))
    seen = [row for page in client.pages(TOY, cap=3, after="4") for row in page]
    assert [row["id"] for row in seen] == [5, 6, 7]


def test_paging_stops_on_a_short_page() -> None:
    client = client_for(fake_register(ROWS, cap=3))
    pages = list(client.pages(TOY, cap=3))
    assert [len(page) for page in pages] == [3, 3, 1]


def test_paging_rejects_a_changed_schema() -> None:
    rows = [{"id": 1, "v": "a", "surprise": 2}]
    client = client_for(fake_register(rows, cap=10))
    with pytest.raises(RegisterSchemaError):
        list(client.pages(TOY, cap=10))


# retries.


def test_transient_failure_is_retried() -> None:
    attempts: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        if len(attempts) < 3:
            return httpx.Response(503)
        return httpx.Response(200, json=[{"id": 1, "v": "a"}])

    client = client_for(httpx.MockTransport(handler))
    assert client.rows("toy", {"limit": 1}) == [{"id": 1, "v": "a"}]
    assert len(attempts) == 3


def test_persistent_failure_gives_up() -> None:
    client = client_for(httpx.MockTransport(lambda _r: httpx.Response(503)))
    with pytest.raises(httpx.HTTPError, match="still failing"):
        client.rows("toy", {"limit": 1})


def test_client_error_is_not_retried() -> None:
    attempts: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        return httpx.Response(404)

    client = client_for(httpx.MockTransport(handler))
    with pytest.raises(httpx.HTTPStatusError):
        client.rows("toy", {"limit": 1})
    assert len(attempts) == 1


def test_a_dataset_filter_reaches_every_request() -> None:
    """The wireless grid is 53.3M rows and only fixed wireless can replace a landline."""
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


def test_a_dataset_without_a_filter_sends_none() -> None:
    seen: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(dict(request.url.params))
        return httpx.Response(200, json=[], headers={"content-range": "*/0"})

    client = client_for(httpx.MockTransport(handler))
    client.count(TOY)
    assert all("or" not in params for params in seen)
