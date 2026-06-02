"""Recording what each provider charges, and when we looked."""

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


def test_a_qualification_code_names_the_line() -> None:
    """The same code comes back from the availability check, which is what joins the two."""
    found = {t.technology: t for t in vodafone.read(VODAFONE_ANSWER)}
    assert found["FTTH"].down_mbps == Decimal(1000)
    assert found["FTTH"].family == "fibre"
    assert found["FWA_5G"].family == "wireless"


def test_a_code_we_do_not_know_is_not_priced() -> None:
    """It would be shown against a line it may not run on."""
    assert "Something New" not in {t.name for t in vodafone.read(VODAFONE_ANSWER)}


def test_equal_prices_are_not_a_discount() -> None:
    """Their feed models one; that it is not running today is not a promotion of nothing."""
    found = {t.technology: t for t in vodafone.read(VODAFONE_ANSWER)}
    assert found["FTTH"].promo_monthly_eur is None
    assert found["FWA_5G"].promo_monthly_eur == Decimal("26.90")


def test_a_home_router_is_part_of_the_offer() -> None:
    found = {t.technology: t for t in vodafone.read(VODAFONE_ANSWER)}
    assert found["FWA_5G"].needs_hardware == "5g_router"
    assert found["FTTH"].needs_hardware is None


def test_the_tariff_key_is_theirs_not_a_name() -> None:
    """Names change with the marketing; the code is what their own systems join on."""
    found = {t.technology: t for t in vodafone.read(VODAFONE_ANSWER)}
    assert found["FTTH"].external_key == "DP Pro UNL - 1Gbps FTTH"


def test_a_nova_package_carries_its_contract() -> None:
    tariffs = nova.read([
        {"code": "2P_FIBER_300", "title": "Fiber 300", "monthly_eur": "23", "contract_months": 24},
        {"code": "2P_VOICE", "title": "Voice", "monthly_eur": "10", "contract_months": 24},
    ])
    assert len(tariffs) == 1
    assert tariffs[0].down_mbps == Decimal(300)
    assert tariffs[0].contract_months == 24
    assert tariffs[0].family == "fibre"


def test_a_price_is_recorded_against_the_day_it_was_seen(
    catalogue: psycopg.Connection[TupleRow],
) -> None:
    """A comparison made last month has to stay answerable after the tariff moves."""
    tariff = Tariff(external_key="X1", name="Test 100", family="fibre",
                    technology="FTTH", down_mbps=Decimal(100), monthly_eur=Decimal("29.90"))
    assert write(catalogue, "OTE", [tariff], TODAY) == 1
    assert write(catalogue, "OTE", [tariff], date(2026, 10, 1)) == 1
    rows = catalogue.execute(
        "select observed_on, monthly_eur from plan_price order by observed_on"
    ).fetchall()
    assert [str(d) for d, _ in rows] == ["2026-09-10", "2026-10-01"]
    assert catalogue.execute("select count(*) from plan").fetchone() == (1,)


def test_looking_twice_in_a_day_corrects_rather_than_doubles(
    catalogue: psycopg.Connection[TupleRow],
) -> None:
    tariff = Tariff(external_key="X1", name="Test", family="fibre", monthly_eur=Decimal(20))
    write(catalogue, "OTE", [tariff], TODAY)
    write(catalogue, "OTE", [Tariff(external_key="X1", name="Test", family="fibre",
                                    monthly_eur=Decimal(25))], TODAY)
    assert catalogue.execute("select monthly_eur from plan_price").fetchall() == [(Decimal(25),)]


def test_an_unknown_setup_fee_stays_unknown(catalogue: psycopg.Connection[TupleRow]) -> None:
    """A catalogue that does not mention one has not said there isn't one."""
    tariff = Tariff(external_key="X1", name="Test", family="fibre", monthly_eur=Decimal(20))
    write(catalogue, "OTE", [tariff], TODAY)
    row = catalogue.execute("select setup_eur, hardware_eur from plan_price").fetchone()
    assert row == (None, None)


def test_every_published_tariff_names_a_known_technology() -> None:
    """A typo in the file would otherwise reach the ranker as a plan on no line at all."""
    from prices.published import load

    for provider, (tariffs, _) in load().items():
        assert tariffs, provider
        for tariff in tariffs:
            assert tariff.technology is not None
            assert tariff.family in {"fibre", "coax", "copper", "wireless", "satellite"}


def test_a_published_tariff_is_dated_by_when_it_was_read() -> None:
    """A rate card read in June is not evidence about September."""
    from prices.published import load

    for provider, (_, observed_on) in load().items():
        assert observed_on.year >= 2026, provider


def test_a_stated_free_fee_is_zero_and_a_silent_one_is_unknown() -> None:
    """Inalan says installation is free; HCN says nothing, and nothing is not free."""
    from prices.published import load

    inalan = {t.external_key: t for t in load()["INALAN"][0]}
    hcn = {t.external_key: t for t in load()["HCN"][0]}
    assert inalan["INALAN_1G"].setup_eur == Decimal(0)
    assert hcn["HCN_SONIC"].setup_eur is None


def test_the_published_technologies_exist_in_the_database(
    catalogue: psycopg.Connection[TupleRow],
) -> None:
    from prices.published import load

    known = {
        str(code) for (code,) in catalogue.execute("select code from technology").fetchall()
    }
    for tariffs, _ in load().values():
        for tariff in tariffs:
            assert tariff.technology in known


def test_the_current_price_view_carries_every_column(
    catalogue: psycopg.Connection[TupleRow],
) -> None:
    """It was written with a star once, and a star is resolved at creation: two columns
    added afterwards were invisible through it until someone happened to select one."""
    stored = {
        str(c) for (c,) in catalogue.execute(
            "select column_name from information_schema.columns where table_name = 'plan_price'"
        ).fetchall()
    }
    shown = {
        str(c) for (c,) in catalogue.execute(
            "select column_name from information_schema.columns "
            "where table_name = 'plan_current'"
        ).fetchall()
    }
    assert stored == shown


def test_a_published_price_says_so(catalogue: psycopg.Connection[TupleRow]) -> None:
    """A rate card and a quote from an ordering system are not the same claim."""
    tariff = Tariff(external_key="X1", name="Test", family="fibre", monthly_eur=Decimal(60))
    write(catalogue, "OTE", [tariff], TODAY, source="published")
    assert catalogue.execute("select source from plan_price").fetchall() == [("published",)]


def test_a_catalogue_price_is_the_default(catalogue: psycopg.Connection[TupleRow]) -> None:
    tariff = Tariff(external_key="X1", name="Test", family="fibre", monthly_eur=Decimal(20))
    write(catalogue, "OTE", [tariff], TODAY)
    assert catalogue.execute("select source from plan_price").fetchall() == [("catalogue",)]


def test_a_provider_publishing_on_two_pages_is_one_provider() -> None:
    """Lines and airtime live on different pages; both are the same company's catalogue."""
    from prices.published import load

    ote = {t.external_key for t in load()["OTE"][0]}
    assert "TELEKOM_FIBER_1G" in ote
    assert "TELEKOM_GIGAMAX_UNLIMITED" in ote


def test_a_data_plan_needs_a_router_the_operator_does_not_give() -> None:
    """That is the difference from a wireless home product, and it is a real cost."""
    from prices.published import load

    plans = {t.external_key: t for t in load()["NOVA"][0]}
    fallback = plans["NOVA_UNLIMITED_ALL"]
    assert fallback.technology == "MOBILE"
    assert fallback.needs_hardware == "5g_router"
    assert fallback.hardware_eur == Decimal(0)
    assert fallback.data_cap_gb is None


def test_an_introductory_price_records_both_halves() -> None:
    """Twelve months at one price and twelve at another is not a plan costing either."""
    from prices.published import load

    red = {t.external_key: t for t in load()["VODAFONE"][0]}["VODAFONE_RED_10"]
    assert red.promo_monthly_eur == Decimal("16.60")
    assert red.promo_months == 12
    assert red.monthly_eur == Decimal("22.14")


def test_the_introductory_blend_beats_neither_half() -> None:
    """The comparable number is the whole contract, which is the point of blending."""
    from prices.published import load
    from ranking.cost import Price, blended

    red = {t.external_key: t for t in load()["VODAFONE"][0]}["VODAFONE_RED_10"]
    cost = blended(Price(
        monthly_eur=red.monthly_eur,
        setup_eur=Decimal(0),
        hardware_eur=red.hardware_eur,
        promo_months=red.promo_months,
        promo_monthly_eur=red.promo_monthly_eur,
    ))
    assert cost is not None
    assert red.promo_monthly_eur is not None
    assert red.promo_monthly_eur < cost.recurring < red.monthly_eur


def test_a_wireless_home_router_costs_more_to_start_than_a_line() -> None:
    """Forty euros against six is most of a year's difference, and the feed states neither."""
    from prices.vodafone import ACTIVATION

    assert ACTIVATION["wireless"] > ACTIVATION["fibre"]
