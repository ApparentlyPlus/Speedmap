"""What every operator's checker is asked and what it answers.

Adapters identify a place differently (coordinates, or the street in their own spelling), so
Target carries enough for all of them and each takes what it needs.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

import psycopg
from psycopg.rows import TupleRow


class ProbeError(RuntimeError):
    """The checker couldn't be asked. That's no answer, and it's never cached."""


class NotAskableError(ProbeError):
    """We hold no spelling for this address, so it can't be put to this operator.

    Our gap, so it's recorded but not counted against the operator's health.
    """


@dataclass(frozen=True)
class Target:
    """One address in every form an operator might want it."""

    address_id: int
    lat: float
    lon: float
    street: str
    street_no: str
    municipality: str
    # their spelling is looked up by id and fold: their municipalities are the
    # pre-Kallikratis ones and mostly don't match ours
    municipality_id: int = 0
    street_fold: str = ""
    locality: str | None = None
    postcode: str | None = None


@dataclass(frozen=True)
class Offer:
    """One technology an operator sells here.

    Speeds are None when they qualified it without quoting one, which is normal for FWA.
    """

    technology: str
    max_down_mbps: Decimal | None = None
    avg_down_mbps: Decimal | None = None
    avg_up_mbps: Decimal | None = None


@dataclass(frozen=True)
class Probed:
    """What one operator said about one address.

    "Not serviceable" is an answer and gets cached. A failure raises instead, and an
    inconclusive reply ("needs looking into by hand") is neither yes nor no.
    """

    serviceable: bool
    offers: tuple[Offer, ...] = ()
    raw: dict[str, object] | None = None
    conclusive: bool = True
    # the raw response, kept only where it's worth the space: canaries and failures
    body: str | None = None


class Adapter(Protocol):
    """An operator's availability checker.

    All take a connection. Two read their spelling of the address with it, and the third
    ignoring it is simpler than callers knowing which is which.
    """

    code: str

    def check(self, conn: psycopg.Connection[TupleRow], target: Target) -> Probed: ...
