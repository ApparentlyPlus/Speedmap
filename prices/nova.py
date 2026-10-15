"""Nova's catalogue. No plan list, so it's read off eligibility answers for real addresses."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from prices.catalogue import Tariff
from probe.adapter import Target
from probe.nova import Nova, euros, speed_of, technology_of

# an answer only lists neighbouring rungs, preselecting 100 never shows the gigabit
PRESELECTIONS = ("2P_FIBER_100", "2P_FIBER_300", "2P_FIBER_500", "2P_FIBER_1000")

FAMILY = {"FTTH": "fiber", "VECT_VDSL": "copper", "VDSL": "copper", "ADSL": "copper"}


@dataclass(frozen=True)
class Reference:
    region: str
    municipality: str
    street: str
    street_no: str
    postcode: str


# their own fiber gets the gigabit tiers, the Athens copper street the rest
REFERENCES = (
    Reference("Ν. ΘΕΣΣΑΛΟΝΙΚΗΣ", "Δ. ΘΕΣΣΑΛΟΝΙΚΗΣ", "ΑΛΕΞΑΝΔΡΟΥ ΣΥΜΕΩΝΙΔΗ", "8", "54639"),
    Reference("Ν. ΑΤΤΙΚΗΣ", "Δ. ΑΘΗΝΑΙΩΝ", "ΑΧΑΡΝΩΝ", "100", "10434"),
)


def read(packages: list[dict[str, object]]) -> list[Tariff]:
    tariffs: list[Tariff] = []
    for p in packages:
        code = str(p.get("code", ""))
        monthly = euros(p.get("monthly_eur"))
        mbps = speed_of(code)
        if monthly is None or mbps is None:
            continue
        technology = technology_of(mbps)
        contract = p.get("contract_months")
        tariffs.append(Tariff(
            external_key=code,
            name=str(p.get("title")),
            family=FAMILY[technology],
            technology=technology,
            down_mbps=Decimal(mbps),
            monthly_eur=monthly,
            contract_months=int(contract) if isinstance(contract, int) else None,
            setup_eur=Decimal(0),  # 50€ on paper, every current offer waives it
        ))
    return tariffs


def fetch(references: tuple[Reference, ...] = REFERENCES) -> list[Tariff]:
    nova = Nova()
    found: dict[str, Tariff] = {}
    for ref in references:
        target = Target(address_id=0, lat=0.0, lon=0.0, street=ref.street, street_no=ref.street_no,
                        municipality=ref.municipality, postcode=ref.postcode)
        for code in PRESELECTIONS:
            probed = nova.ask(target, ref.region, ref.municipality, {"code": code, "title": code, "price": "29.0"})
            raw = probed.raw if probed.raw is not None else {}
            packages = raw.get("packages")
            if not isinstance(packages, list):
                continue
            for t in read(packages):
                found.setdefault(t.external_key, t)
    return sorted(found.values(), key=lambda t: t.monthly_eur)
