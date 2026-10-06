"""Nova's catalogue, which they only publish one address at a time.

They have no plan list: the eligibility answer carries the tariff, and only the plans that
qualify at the address asked about.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from prices.catalogue import Tariff
from probe.adapter import Target
from probe.nova import Nova, euros, speed_of, technology_of

# An answer only covers the rung asked about and its neighbours, so we sweep the catalogue.
# Preselecting 100 never mentions that a gigabit exists.
PRESELECTIONS = ("2P_FIBER_100", "2P_FIBER_300", "2P_FIBER_500", "2P_FIBER_1000")

FAMILY = {"FTTH": "fiber", "VECT_VDSL": "copper", "VDSL": "copper", "ADSL": "copper"}


@dataclass(frozen=True)
class Reference:
    """A real address, used only to get them to quote."""

    region: str
    municipality: str
    street: str
    street_no: str
    postcode: str


# Between them these show every rung they sell: a street on their own fiber gets the gigabit
# tiers, an Athens copper street the rest.
REFERENCES = (
    Reference("Ν. ΘΕΣΣΑΛΟΝΙΚΗΣ", "Δ. ΘΕΣΣΑΛΟΝΙΚΗΣ", "ΑΛΕΞΑΝΔΡΟΥ ΣΥΜΕΩΝΙΔΗ", "8", "54639"),
    Reference("Ν. ΑΤΤΙΚΗΣ", "Δ. ΑΘΗΝΑΙΩΝ", "ΑΧΑΡΝΩΝ", "100", "10434"),
)


def read(packages: list[dict[str, object]]) -> list[Tariff]:
    """Their packages in our vocabulary. A code without a speed names no line."""
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
            # Their tariff puts activation at 50€ and every current offer waives it, so it's
            # recorded as waived, which is what a new customer pays.
            setup_eur=Decimal(0),
        ))
    return tariffs


def fetch(references: tuple[Reference, ...] = REFERENCES) -> list[Tariff]:
    """Every plan the reference addresses qualify for between them, deduplicated by code."""
    nova = Nova()
    found: dict[str, Tariff] = {}
    for reference in references:
        target = Target(
            address_id=0, lat=0.0, lon=0.0,
            street=reference.street, street_no=reference.street_no,
            municipality=reference.municipality, postcode=reference.postcode,
        )
        for code in PRESELECTIONS:
            preselect = {"code": code, "title": code, "price": "29.0"}
            probed = nova.ask(target, reference.region, reference.municipality, preselect)
            raw = probed.raw if probed.raw is not None else {}
            packages = raw.get("packages")
            if not isinstance(packages, list):
                continue
            for tariff in read(packages):
                found.setdefault(tariff.external_key, tariff)
    return sorted(found.values(), key=lambda t: t.monthly_eur)
