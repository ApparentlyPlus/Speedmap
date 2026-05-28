"""What every operator's checker is asked, and what it is expected to answer with.

Adapters differ in what they need to identify a place: one takes coordinates, another the
same street name spelled the way it spells it. Target carries enough for all of them and
each takes what it uses.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol


@dataclass(frozen=True)
class Target:
    """One address, in every form an operator might want to be given it."""

    address_id: int
    lat: float
    lon: float
    street: str
    street_no: str
    municipality: str
    locality: str | None = None
    postcode: str | None = None


@dataclass(frozen=True)
class Offer:
    """One technology an operator will sell here, with what it promises over it.

    Speeds are None when the operator qualified the technology without quoting one, which
    is normal for wireless: the answer is that it reaches here, not how fast.
    """

    technology: str
    max_down_mbps: Decimal | None = None
    avg_down_mbps: Decimal | None = None
    avg_up_mbps: Decimal | None = None


@dataclass(frozen=True)
class Probed:
    """What one operator said about one address.

    Not serviceable is an answer and is cached like any other. A checker that failed is not
    this: it raises, and nothing is written, because a failure is not a refusal.

    Nor is an inconclusive answer. One operator replies that an address needs looking into
    by hand, which is neither yes nor no, and writing it down as either would be a lie the
    cache then repeats for six months.
    """

    serviceable: bool
    offers: tuple[Offer, ...] = ()
    raw: dict[str, object] | None = None
    conclusive: bool = True


class Adapter(Protocol):
    """An operator's availability checker."""

    code: str

    def check(self, target: Target) -> Probed: ...
