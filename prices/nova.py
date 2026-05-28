"""Nova's catalogue, which they publish only one address at a time.

They have no plan list of their own: the eligibility answer carries the tariff, and it
carries only the plans that qualify at the address asked about. The prices in it are
national, so a handful of addresses chosen to span the technologies reconstructs the
catalogue, and a fibre address is the only place the gigabit rungs ever appear.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from prices.catalogue import Tariff
from probe.adapter import Target
from probe.nova import Nova, euros, speed_of, technology_of

FAMILY = {"FTTH": "fibre", "VECT_VDSL": "copper", "VDSL": "copper", "ADSL": "copper"}


@dataclass(frozen=True)
class Reference:
    """A real address, used only to make them quote."""

    region: str
    municipality: str
    street: str
    street_no: str
    postcode: str


# Two addresses in Athens: one on fibre, one on copper. Between them every rung they sell
# has somewhere to appear. Neither is queried for its own sake.
REFERENCES = (
    Reference("Ν. ΑΤΤΙΚΗΣ", "Δ. ΑΘΗΝΑΙΩΝ", "ΑΓΙΟΥ ΛΟΥΚΑ", "1", "11254"),
    Reference("Ν. ΑΤΤΙΚΗΣ", "Δ. ΑΘΗΝΑΙΩΝ", "ΑΧΑΡΝΩΝ", "100", "10434"),
)


def read(packages: list[dict[str, object]]) -> list[Tariff]:
    """Their packages, in our vocabulary. A code with no speed in it names no line."""
    tariffs: list[Tariff] = []
    for package in packages:
        code = str(package.get("code", ""))
        monthly = euros(package.get("monthly_eur"))
        mbps = speed_of(code)
        if monthly is None or mbps is None:
            continue
        technology = technology_of(mbps)
        contract = package.get("contract_months")
        tariffs.append(Tariff(
            external_key=code,
            name=str(package.get("title")),
            family=FAMILY[technology],
            technology=technology,
            down_mbps=Decimal(mbps),
            monthly_eur=monthly,
            contract_months=int(contract) if isinstance(contract, int) else None,
        ))
    return tariffs


def fetch(references: tuple[Reference, ...] = REFERENCES) -> list[Tariff]:
    """Every plan the reference addresses between them qualify for, deduplicated by code."""
    nova = Nova()
    found: dict[str, Tariff] = {}
    for reference in references:
        target = Target(
            address_id=0, lat=0.0, lon=0.0,
            street=reference.street, street_no=reference.street_no,
            municipality=reference.municipality, postcode=reference.postcode,
        )
        probed = nova.check(target, reference.region, reference.municipality)
        raw = probed.raw if probed.raw is not None else {}
        packages = raw.get("packages")
        if not isinstance(packages, list):
            continue
        for tariff in read(packages):
            found.setdefault(tariff.external_key, tariff)
    return sorted(found.values(), key=lambda t: t.monthly_eur)
