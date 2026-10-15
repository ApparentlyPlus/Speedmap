from __future__ import annotations

from decimal import Decimal

from ranking.cost import Price, blended
from ranking.offer import owned, speed
from ranking.rank import BEST, FASTEST, FROM, SHORT, Option, Ranked, rank


def _option(provider: str, plan: str, family: str, mbps: object, monthly: object, *, technology: str = "FTTH",
            hardware: object = 0, setup: object = 0) -> Option:
    cost = blended(Price(
        monthly_eur=Decimal(str(monthly)),
        setup_eur=None if setup is None else Decimal(str(setup)),
        hardware_eur=None if hardware is None else Decimal(str(hardware)),
    ))
    return Option(provider=provider, provider_name=provider.title(), plan=plan, technology=technology, family=family,
                  expected_mbps=None if mbps is None else Decimal(str(mbps)), cost=cost)


def _gigamax(gb: int | None, mbps: int, monthly: str) -> Option:
    return Option(
        provider="TELEKOM", provider_name="Telekom", plan=f"gigamax {gb}", technology="MOBILE", family="wireless",
        expected_mbps=Decimal(mbps),
        cost=blended(Price(monthly_eur=Decimal(monthly), setup_eur=Decimal(0), hardware_eur=Decimal(0))),
        data_cap_gb=gb,
    )


def _plans(ranked: list[Ranked]) -> list[str]:
    return [r.option.plan for r in ranked]


def test_rank_enough() -> None:
    found = rank([
        _option("DEI", "fiber 1G", "fiber", 1000, "19.90"),
        _option("NOVA", "fiber 100", "copper", 100, "21", technology="VECT_VDSL"),
        _option("VODAFONE", "fiber 300", "fiber", 300, "24.22"),
    ])
    assert _plans(found) == ["fiber 1G", "fiber 300", "fiber 100"]
    assert found[0].why == BEST
    assert all(r.enough for r in found)

    found = rank([
        _option("TELEKOM", "gigamax", "wireless", 240, "30.00", technology="MOBILE"),
        _option("INALAN", "inalan 1G", "fiber", 1000, "34.00"),
    ])
    assert _plans(found) == ["inalan 1G", "gigamax"]

    # above the bar extra speed is worth nothing
    found = rank([
        _option("DEI", "fiber 2.5G", "fiber", 2500, "52.90"),
        _option("NOVA", "fiber 300", "fiber", 300, "23"),
    ])
    assert _plans(found) == ["fiber 300", "fiber 2.5G"]

    found = rank([
        _option("TELEKOM", "5g wifi", "wireless", 300, "30.90", technology="FWA_5G"),
        _option("TELEKOM", "fiber 500", "fiber", 500, "30.90"),
    ])
    assert _plans(found) == ["fiber 500", "5g wifi"]

    found = rank([
        _option("STARLINK", "starlink", "satellite", 100, "35", hardware=0),
        _option("TELEKOM", "5g wifi", "wireless", 100, "35", technology="FWA_5G"),
        _option("NOVA", "fiber", "fiber", 100, "35"),
    ])
    assert _plans(found) == ["fiber", "5g wifi", "starlink"]

    # 349€ of dish is 14,54 a month
    found = rank([
        _option("STARLINK", "starlink", "satellite", 100, "35", hardware=349),
        _option("TELEKOM", "5g wifi", "wireless", 300, "35.90", technology="FWA_5G", hardware=0),
    ])
    assert _plans(found) == ["5g wifi", "starlink"]


def test_rank_short() -> None:
    found = rank([
        _option("TELEKOM", "adsl 24", "copper", 24, "19.90", technology="ADSL"),
        _option("VODAFONE", "vdsl 50", "copper", 50, "26", technology="VDSL"),
    ])
    assert _plans(found) == ["vdsl 50", "adsl 24"]
    assert found[0].why == FASTEST
    assert found[1].why == SHORT
    assert not any(r.enough for r in found)

    found = rank([
        _option("VODAFONE", "wireless home", "wireless", None, "26.90", technology="FWA"),
        _option("TELEKOM", "adsl", "copper", 24, "24", technology="ADSL"),
    ])
    assert _plans(found) == ["adsl", "wireless home"]
    assert not any(r.enough for r in found)

    assert rank([]) == []

    options = [
        _option("DEI", "fiber 1G", "fiber", 1000, "19.90"),
        _option("NOVA", "fiber 100", "copper", 100, "21", technology="VECT_VDSL"),
    ]
    assert rank(options, need=Decimal(500))[0].option.plan == "fiber 1G"
    assert rank(options, need=Decimal(500))[1].enough is False


def test_rank_floor() -> None:
    # HCN publishes no setup fee, still ranks on its monthly
    found = rank([
        _option("HCN", "sonic", "fiber", 1000, "23", setup=None),
        _option("NOVA", "fiber 100", "copper", 100, "21", technology="VECT_VDSL"),
    ])
    assert _plans(found) == ["sonic", "fiber 100"]
    assert found[0].why == FROM
    assert found[0].enough is True
    assert found[0].option.cost.complete is False
    assert found[0].option.cost.total == Decimal("23")

    found = rank([_option("NOVA", "fiber 100", "copper", 100, "21", technology="VECT_VDSL")])
    assert found[0].option.cost.complete is True
    assert found[0].why != FROM


def test_rank_metered() -> None:
    found = rank([_gigamax(9, 240, "24.00"), _gigamax(None, 240, "41.00")])
    assert _plans(found) == ["gigamax None", "gigamax 9"]
    assert found[0].enough is True
    assert found[1].enough is False

    # 70 GB is a fortnight of one TV
    assert rank([_gigamax(70, 300, "36.00")])[0].enough is False
    assert rank([_gigamax(500, 300, "36.00")])[0].enough is True

    found = rank([
        _gigamax(9, 240, "24.00"),
        _option("TELEKOM", "5g wifi", "wireless", 240, "35.90", technology="FWA_5G"),
    ])
    assert _plans(found) == ["5g wifi", "gigamax 9"]


def test_rank_satellite() -> None:
    found = rank([
        _gigamax(None, 8, "41.00"),
        _option("STARLINK", "starlink 200", "satellite", 140, "45", hardware=349),
        _option("STARLINK", "starlink 100", "satellite", 70, "35", hardware=349),
    ])
    assert _plans(found)[0] == "starlink 200"
    assert found[0].enough is True
    assert found[1].enough is False

    found = rank([
        _gigamax(None, 240, "41.00"),
        _option("STARLINK", "starlink 200", "satellite", 140, "45", hardware=349),
    ])
    assert _plans(found)[0] == "gigamax None"


def test_offer_speed() -> None:
    assert speed("wireless", Decimal(50), None, None, Decimal(300), None).mbps == Decimal(50)
    assert speed("wireless", Decimal(300), None, None, Decimal(300), None).mbps == Decimal(240)
    # Telekom guarantees 93 on a plan sold as 100
    assert speed("copper", Decimal(100), Decimal(100), Decimal(93), None, None).mbps == Decimal(93)

    assert owned(None, None) == Decimal(0)
    assert owned("dish", None) is None
    assert owned("dish", Decimal(349)) == Decimal(349)
