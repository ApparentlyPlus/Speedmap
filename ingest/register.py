"""
Client for the national broadband register's PostgREST API.

The register caps a page without saying so: a request for 20000 rows returns 200
with 500 of them, no header and no error. The cap is therefore measured at the
start of a run rather than trusted, and paging is by key rather than offset so a
resumed run cannot skip or repeat rows if the data shifts underneath it.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from typing import Any

import httpx

BASE_URL = "https://www.broadband-assist.gov.gr/api"

RETRYABLE = frozenset({429, 500, 502, 503, 504})


class RegisterSchemaError(RuntimeError):
    """A dataset came back with columns we do not know about."""


@dataclass(frozen=True)
class Dataset:
    name: str
    path: str
    key: str
    columns: frozenset[str]


DATASETS: tuple[Dataset, ...] = (
    Dataset(
        "provider",
        "provider",
        "id",
        frozenset({"id", "name", "short_name"}),
    ),
    Dataset(
        "coverpoint",
        "a3b_coverpointftthcoax",
        "coverid",
        frozenset(
            {
                "infrprov",
                "coverid",
                "method",
                "infrstar",
                "prempass",
                "connstat",
                "intcabl",
                "vhcn",
                "address",
                "point",
                "waitpoin",
                "bngid",
            }
        ),
    ),
    Dataset(
        "wiredservice",
        "a4a_wiredservice",
        "id",
        frozenset(
            {
                "servprov",
                "infrprov",
                "coverid",
                "technolo",
                "ownrship",
                "maxdown",
                "nordown",
                "maxup",
                "norup",
                "servstar",
                "covermod",
                "id",
            }
        ),
    ),
    Dataset(
        "coverage_ftth",
        "coverage_ftth",
        "id",
        frozenset(
            {
                "id",
                "coverid",
                "servprov_ids",
                "technolo_ids",
                "maxdown_ids",
                "ownrship_ids",
                "servstar_years",
                "servstar_quarters",
                "dimos_id",
                "geom",
            }
        ),
    ),
    Dataset(
        "coverage_copper",
        "coverage_copper",
        "id",
        frozenset(
            {
                "id",
                "coverid",
                "servprov_ids",
                "technolo_ids",
                "maxdown_ids",
                "ownrship_ids",
                "servstar_years",
                "servstar_quarters",
                "dimos_id",
                "geom",
            }
        ),
    ),
    Dataset(
        "geo_coverage_copper",
        "geo_coverage_copper",
        "coverid",
        frozenset(
            {
                "coverid",
                "servprov_ids",
                "technolo_ids",
                "maxdown_ids",
                "ownrship_ids",
                "dimos_id",
                "geom",
            }
        ),
    ),
)

BY_NAME = {dataset.name: dataset for dataset in DATASETS}

# The code tables. Small enough to take whole, and every one of them is a
# vocabulary some numeric column indexes into.
LOOKUPS: tuple[str, ...] = (
    "a3b_connstat",
    "a3b_intcabl",
    "a3b_method",
    "a3b_vhcn",
    "a4a_maxdown",
    "a4a_maxup",
    "a4a_nordown",
    "a4a_norup",
    "a4a_ownrship",
    "a4a_technolo",
)

Row = dict[str, Any]


class RegisterClient:
    def __init__(
        self,
        client: httpx.Client,
        *,
        base_url: str = BASE_URL,
        delay_s: float = 0.35,
        max_tries: int = 4,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.client = client
        self.base_url = base_url.rstrip("/")
        self.delay_s = delay_s
        self.max_tries = max_tries
        self.sleep = sleep

    def _get(
        self,
        path: str,
        params: Mapping[str, str | int],
        headers: Mapping[str, str] | None = None,
    ) -> httpx.Response:
        url = f"{self.base_url}/{path}"
        for attempt in range(self.max_tries):
            response = self.client.get(url, params=dict(params), headers=headers)
            if response.status_code not in RETRYABLE:
                response.raise_for_status()
                self.sleep(self.delay_s)
                return response
            self.sleep(retry_delay(response, attempt))
        raise httpx.HTTPError(f"{url}: still failing after {self.max_tries} tries")

    def rows(self, path: str, params: Mapping[str, str | int]) -> list[Row]:
        body = self._get(path, params).json()
        if not isinstance(body, list):
            raise RegisterSchemaError(f"{path}: expected a list of rows")
        return list(body)

    def count(self, dataset: Dataset) -> int | None:
        """Exact row count. PostgREST only counts when asked, and not every view answers."""
        response = self._get(
            dataset.path,
            {"select": dataset.key, "limit": 1},
            headers={"prefer": "count=exact"},
        )
        return parse_total(response.headers.get("content-range"))

    def page_cap(self, dataset: Dataset, *, probe: int = 2000) -> int:
        """Measure the cap by asking for more than it will give."""
        rows = self.rows(dataset.path, {"select": dataset.key, "limit": probe})
        if len(rows) == probe:
            return probe
        total = self.count(dataset)
        if total is not None and len(rows) == total:
            return probe
        return max(len(rows), 1)

    def pages(self, dataset: Dataset, *, cap: int, after: str | None = None) -> Iterator[list[Row]]:
        """Yield pages in key order, resuming after the given key."""
        cursor = after
        while True:
            params: dict[str, str | int] = {
                "select": "*",
                "order": f"{dataset.key}.asc",
                "limit": cap,
            }
            if cursor is not None:
                params[dataset.key] = f"gt.{cursor}"

            rows = self.rows(dataset.path, params)
            if not rows:
                return

            check_columns(dataset, rows[0])
            yield rows

            if len(rows) < cap:
                return
            cursor = str(rows[-1][dataset.key])

    def lookup(self, table: str) -> list[Row]:
        return self.rows(table, {"select": "*", "limit": 500})


def check_columns(dataset: Dataset, row: Row) -> None:
    """A changed column set means the register was redesigned, not that a row is odd."""
    seen = frozenset(row)
    if seen != dataset.columns:
        added = sorted(seen - dataset.columns)
        removed = sorted(dataset.columns - seen)
        raise RegisterSchemaError(f"{dataset.path}: added={added} removed={removed}")


def parse_total(content_range: str | None) -> int | None:
    """'0-0/2673805' carries the total; '*/*' and a missing header do not."""
    if content_range is None or "/" not in content_range:
        return None
    total = content_range.rsplit("/", 1)[1].strip()
    return int(total) if total.isdigit() else None


def retry_delay(response: httpx.Response, attempt: int) -> float:
    """Honour Retry-After when the server sends a number, else back off."""
    header = response.headers.get("retry-after", "")
    if header.strip().isdigit():
        return float(header.strip())
    return float(2**attempt)
