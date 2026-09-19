"""What every operator's checker is asked, and what it answers with.

Adapters need different things to identify a place, coordinates, or the street spelled
their way, so Target carries enough for all of them and each takes what it uses.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

import psycopg
from psycopg.rows import TupleRow


class ProbeError(RuntimeError):
    """The checker could not be asked. Not an answer, and never cached as one."""


class NotAskableError(ProbeError):
    """We hold no spelling for this address, so it cannot be put to this operator.

    Our gap, not theirs: recorded, but not counted against the operator's health.
    """


@dataclass(frozen=True)
class Target:
    """One address, in every form an operator might want to be given it."""

    address_id: int
    lat: float
    lon: float
    street: str
    street_no: str
    municipality: str
    # Their spelling is looked up by id and fold, not by name: their municipalities are the
    # pre-Kallikratis ones and mostly do not share ours.
    municipality_id: int = 0
    street_fold: str = ""
    locality: str | None = None
    postcode: str | None = None


@dataclass(frozen=True)
class Offer:
    """One technology an operator will sell here.

    Speeds are None when they qualified the technology without quoting one, normal for FWA.
    """

    technology: str
    max_down_mbps: Decimal | None = None
    avg_down_mbps: Decimal | None = None
    avg_up_mbps: Decimal | None = None


@dataclass(frozen=True)
class Probed:
    """What one operator said about one address.

    Not serviceable is an answer and is cached. A failure raises instead, and an
    inconclusive reply ("needs looking into by hand") is neither yes nor no.
    """

    serviceable: bool
    offers: tuple[Offer, ...] = ()
    raw: dict[str, object] | None = None
    conclusive: bool = True
    # The response as it arrived, kept only where it earns its size: canaries and failures.
    body: str | None = None


class Adapter(Protocol):
    """An operator's availability checker.

    All of them take a connection. Two need it to read how they spell the address, and the
    third ignoring it is cheaper than the caller knowing which is which.
    """

    code: str

    def check(self, conn: psycopg.Connection[TupleRow], target: Target) -> Probed: ...
