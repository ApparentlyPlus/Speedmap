from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from typing import Any

import psycopg
import pytest
from psycopg.rows import TupleRow

from prices import nova, vodafone
from prices.catalogue import Tariff, write
from prices.published import load
from prices.vodafone import ACTIVATION
from ranking.cost import Price, blended

TODAY = date(2026, 9, 10)

VODAFONE_ANSWER: dict[str, Any] = {
    "subCategory": [{"productOffering": [
        {
            "name": "Full Fiber 1Gbps plus",
            "productSpecification": {"externalIdentifier": [
                {"externalIdentifierType": "AvToolCode", "id": "FTTH_1000"},
                {"externalIdentifierType": "TariffPlanCode", "id": "DP Pro UNL - 1Gbps FTTH"},
            ]},
            "productOfferingPrice": [
                {"name": "salePrice", "price": {"taxIncludedAmount": {"value": 31.33}}},
                {"name": "initialPrice", "price": {"taxIncludedAmount": {"value": 31.33}}},
            ],
        },
        {
            "name": "Vodafone Wireless Home 5G",
            "productSpecification": {"externalIdentifier": [
                {"externalIdentifierType": "AvToolCode", "id": "FWA 5G"},
            ]},
            "productOfferingPrice": [
                {"name": "salePrice", "price": {"taxIncludedAmount": {"value": 26.90}}},
                {"name": "initialPrice", "price": {"taxIncludedAmount": {"value": 34.90}}},
            ],
        },
        {
            "name": "Something New",
            "productSpecification": {"externalIdentifier": [
                {"externalIdentifierType": "AvToolCode", "id": "FTTH_2000"},
            ]},
            "productOfferingPrice": [
                {"name": "salePrice", "price": {"taxIncludedAmount": {"value": 40.0}}},
            ],
        },
    ]}]
}


@pytest.fixture
def catalogue(db: psycopg.Connection[TupleRow]) -> Iterator[psycopg.Connection[TupleRow]]:
    db.execute("truncate plan_price, plan cascade")
    db.commit()
    yield db
    db.execute("truncate plan_price, plan cascade")
    db.commit()


def _clear(conn: psycopg.Connection[TupleRow]) -> None:
    conn.execute("truncate plan_price, plan cascade")
    conn.commit()


def _tariff(monthly: object) -> Tariff:
    return Tariff(external_key="X1", name="Test", family="fiber", monthly_eur=Decimal(str(monthly)))


def _plans(provider: str) -> dict[str, Tariff]:
    return {t.external_key: t for t in load()[provider][0]}


def test_vodafone_read() -> None:
    found = {t.technology: t for t in vodafone.read(VODAFONE_ANSWER)}
    # same code the availability check answers in
    assert found["FTTH"].down_mbps == Decimal(1000)
    assert found["FTTH"].family == "fiber"
    assert found["FWA_5G"].family == "wireless"
    assert "Something New" not in {t.name for t in vodafone.read(VODAFONE_ANSWER)}

    # equal prices mean no discount running
    assert found["FTTH"].promo_monthly_eur is None
    assert found["FWA_5G"].promo_monthly_eur == Decimal("26.90")
    assert found["FWA_5G"].needs_hardware == "5g_router"
    assert found["FTTH"].needs_hardware is None
    assert found["FTTH"].external_key == "DP Pro UNL - 1Gbps FTTH"

    assert ACTIVATION["wireless"] > ACTIVATION["fiber"]


def test_nova_read() -> None:
    tariffs = nova.read([
        {"code": "2P_FIBER_300", "title": "Fiber 300", "monthly_eur": "23", "contract_months": 24},
        {"code": "2P_VOICE", "title": "Voice", "monthly_eur": "10", "contract_months": 24},
    ])
    assert len(tariffs) == 1
    assert tariffs[0].down_mbps == Decimal(300)
    assert tariffs[0].contract_months == 24
    assert tariffs[0].family == "fiber"


def test_write(catalogue: psycopg.Connection[TupleRow]) -> None:
    tariff = Tariff(external_key="X1", name="Test 100", family="fiber", technology="FTTH", down_mbps=Decimal(100),
                    monthly_eur=Decimal("29.90"))
    assert write(catalogue, "TELEKOM", [tariff], TODAY) == 1
    assert write(catalogue, "TELEKOM", [tariff], date(2026, 10, 1)) == 1
    rows = catalogue.execute("select observed_on, monthly_eur from plan_price order by observed_on").fetchall()
    assert [str(d) for d, _ in rows] == ["2026-09-10", "2026-10-01"]
    assert catalogue.execute("select count(*) from plan").fetchone() == (1,)

    # same day twice overwrites
    _clear(catalogue)
    write(catalogue, "TELEKOM", [_tariff(20)], TODAY)
    write(catalogue, "TELEKOM", [_tariff(25)], TODAY)
    assert catalogue.execute("select monthly_eur from plan_price").fetchall() == [(Decimal(25),)]

    _clear(catalogue)
    write(catalogue, "TELEKOM", [_tariff(20)], TODAY)
    assert catalogue.execute("select setup_eur, hardware_eur from plan_price").fetchone() == (None, None)
    assert catalogue.execute("select source from plan_price").fetchall() == [("catalogue",)]

    _clear(catalogue)
    write(catalogue, "TELEKOM", [_tariff(60)], TODAY, source="published")
    assert catalogue.execute("select source from plan_price").fetchall() == [("published",)]


def test_plan_current(catalogue: psycopg.Connection[TupleRow]) -> None:
    # it was once a select *, which froze the column list
    q = "select column_name from information_schema.columns where table_name = %s"
    stored = {str(c) for (c,) in catalogue.execute(q, ("plan_price",)).fetchall()}
    shown = {str(c) for (c,) in catalogue.execute(q, ("plan_current",)).fetchall()}
    assert stored == shown


def test_published(catalogue: psycopg.Connection[TupleRow]) -> None:
    known = {str(code) for (code,) in catalogue.execute("select code from technology").fetchall()}
    for provider, (tariffs, observed_on) in load().items():
        assert tariffs, provider
        assert observed_on.year >= 2026, provider
        for t in tariffs:
            assert t.technology is not None
            assert t.family in {"fiber", "coax", "copper", "wireless", "satellite"}
            assert t.technology in known

    # Inalan says installation is free, HCN only says so for Sonic
    assert _plans("INALAN")["INALAN_1G"].setup_eur == Decimal(0)
    hcn = _plans("HCN")
    assert hcn["HCN_SONIC"].setup_eur == Decimal(0)
    assert hcn["HCN_STELLAR"].setup_eur is None

    # lines and airtime are different pages
    ote = set(_plans("TELEKOM"))
    assert "TELEKOM_FIBER_1G" in ote
    assert "TELEKOM_GIGAMAX_UNLIMITED" in ote

    # Starlink files nothing in the register, but sells everywhere
    assert load()["STARLINK"][0]


def test_published_hardware() -> None:
    fallback = _plans("NOVA")["NOVA_UNLIMITED_ALL"]
    assert fallback.technology == "MOBILE"
    assert fallback.needs_hardware == "5g_router"
    assert fallback.hardware_eur == Decimal(0)
    assert fallback.data_cap_gb is None

    dish = _plans("STARLINK")["STARLINK_RESIDENTIAL_100"]
    assert dish.needs_hardware == "dish"
    assert dish.hardware_eur == Decimal(349)
    router = _plans("TELEKOM")["TELEKOM_5G_WIFI_DP_300"]
    assert router.needs_hardware == "5g_router"
    assert router.hardware_eur == Decimal(0)

    def monthly(t: Tariff) -> Decimal:
        cost = blended(Price(monthly_eur=t.monthly_eur, setup_eur=t.setup_eur if t.setup_eur is not None else Decimal(0),
                             hardware_eur=t.hardware_eur))
        assert cost is not None
        return cost.total

    # the dish is cheaper on paper and dearer once bought
    assert dish.monthly_eur < router.monthly_eur
    assert monthly(dish) > monthly(router)


def test_published_promo() -> None:
    red = _plans("VODAFONE")["VODAFONE_RED_10"]
    assert red.promo_monthly_eur == Decimal("16.60")
    assert red.promo_months == 12
    assert red.monthly_eur == Decimal("22.14")

    cost = blended(Price(monthly_eur=red.monthly_eur, setup_eur=Decimal(0), hardware_eur=red.hardware_eur,
                         promo_months=red.promo_months, promo_monthly_eur=red.promo_monthly_eur))
    assert cost is not None
    assert red.promo_monthly_eur is not None
    assert red.promo_monthly_eur < cost.recurring < red.monthly_eur
