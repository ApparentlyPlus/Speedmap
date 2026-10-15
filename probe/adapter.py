"""What every operator's checker is asked and what it answers."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

import psycopg
from psycopg.rows import TupleRow


class ProbeError(RuntimeError):
    """The checker couldn't be asked. Never cached."""


class NotAskableError(ProbeError):
    """No spelling of this address for this operator. Our gap, not held against their health."""


@dataclass(frozen=True)
class Target:
    # every form any operator might want
    address_id: int
    lat: float
    lon: float
    street: str
    street_no: str
    municipality: str
    # for looking up their spelling, their municipalities are pre-Kallikratis
    municipality_id: int = 0
    street_fold: str = ""
    locality: str | None = None
    postcode: str | None = None


@dataclass(frozen=True)
class Offer:
    technology: str
    max_down_mbps: Decimal | None = None  # None when qualified without a speed, normal for FWA
    avg_down_mbps: Decimal | None = None
    avg_up_mbps: Decimal | None = None


@dataclass(frozen=True)
class Probed:
    serviceable: bool
    offers: tuple[Offer, ...] = ()
    raw: dict[str, object] | None = None
    conclusive: bool = True  # False for "needs looking into by hand"
    body: str | None = None  # raw response, canaries and failures only


class Adapter(Protocol):
    code: str

    # conn is for the adapters that look up their own spelling
    def check(self, conn: psycopg.Connection[TupleRow], target: Target) -> Probed: ...
