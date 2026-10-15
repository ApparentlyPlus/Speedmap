from __future__ import annotations

from decimal import Decimal
from typing import Any

from probe.adapter import Target
from probe.nova import Nova, euros, read, speed_of, technology_of

ANSWER: dict[str, Any] = {
    "result": {
        "formattedAddress": "ΑΧΑΡΝΩΝ 100 (10434)",
        "packages": [
            {"code": "2P_FIBER_100", "title": "Fiber 100", "monthlyFeeDisplay": "21", "bindPeriod": 24},
            {"code": "2P_FIBER_300", "title": "Fiber 300", "monthlyFeeDisplay": "23", "bindPeriod": 24},
            {"code": "3P_FIBER_100_EON", "title": "Fiber 100 EON", "monthlyFeeDisplay": "29", "bindPeriod": 24},
        ],
    }
}

ACHARNON = [
    {"street": "ΑΧΑΡΝΩΝ", "zipcode": "10432", "city": "ΑΘΗΝΑ"},
    {"street": "ΑΧΑΡΝΩΝ", "zipcode": "10434", "city": "ΑΘΗΝΑ"},
]


def test_speed_of() -> None:
    assert speed_of("2P_FIBER_100") == 100
    assert speed_of("3P_FIBER_100_EON_PLUS") == 100
    assert speed_of("2P_FIBER_1G") == 1000
    assert speed_of("2P_ADSL") is None

    # FIBER covers copper too
    assert technology_of(1000) == "FTTH"
    assert technology_of(300) == "FTTH"
    assert technology_of(100) == "VECT_VDSL"
    assert technology_of(50) == "VDSL"
    assert technology_of(24) == "ADSL"


def test_read() -> None:
    found = {o.technology: o for o in read(ANSWER).offers}
    assert found["FTTH"].max_down_mbps == Decimal(300)
    assert found["VECT_VDSL"].max_down_mbps == Decimal(100)

    raw = read(ANSWER).raw
    assert raw is not None
    packages = raw["packages"]
    assert isinstance(packages, list)
    assert packages[0] == {"code": "2P_FIBER_100", "title": "Fiber 100", "monthly_eur": "21", "contract_months": 24}

    assert read({"result": {"packages": []}}).serviceable is False
    assert read({"result": {"packages": None}}).serviceable is False
    assert read({}).serviceable is False


def test_euros() -> None:
    assert euros("21,50") == Decimal("21.50")
    assert euros("21.50") == Decimal("21.50")
    assert euros(None) is None
    assert euros("—") is None


def test_locate() -> None:
    # ΑΧΑΡΝΩΝ spans three postcodes
    nova = Nova()
    nova.seen[("Ν. ΑΤΤΙΚΗΣ", "Δ. ΑΘΗΝΑΙΩΝ", "Α")] = ACHARNON
    target = Target(address_id=1, lat=0, lon=0, street="ΑΧΑΡΝΩΝ", street_no="100",
                    municipality="ΔΗΜΟΣ ΑΘΗΝΑΙΩΝ", postcode="10434")
    found = nova.locate(target, "Ν. ΑΤΤΙΚΗΣ", "Δ. ΑΘΗΝΑΙΩΝ")
    assert found is not None
    assert found["zipcode"] == "10434"

    # no postcode, don't guess
    target = Target(address_id=1, lat=0, lon=0, street="ΑΧΑΡΝΩΝ", street_no="100",
                    municipality="ΔΗΜΟΣ ΑΘΗΝΑΙΩΝ", postcode=None)
    assert nova.locate(target, "Ν. ΑΤΤΙΚΗΣ", "Δ. ΑΘΗΝΑΙΩΝ") is None
