"""Ordering what someone can buy, across the shapes an address actually comes in."""

from __future__ import annotations

from decimal import Decimal

from ranking.cost import Price, blended
from ranking.rank import BEST, FASTEST, FROM, SHORT, Option, Ranked, rank


def option(
    provider: str, plan: str, family: str, mbps: object, monthly: object,
    *, technology: str = "FTTH", hardware: object = 0, setup: object = 0,
) -> Option:
    cost = blended(Price(
        monthly_eur=Decimal(str(monthly)),
        setup_eur=None if setup is None else Decimal(str(setup)),
        hardware_eur=None if hardware is None else Decimal(str(hardware)),
    ))
    return Option(
        provider=provider, provider_name=provider.title(), plan=plan,
        technology=technology, family=family,
        expected_mbps=None if mbps is None else Decimal(str(mbps)), cost=cost,
    )


def order(ranked: list[Ranked]) -> list[str]:
    return [r.option.plan for r in ranked]


def test_a_line_comes_first_and_then_the_cheapest_of_them() -> None:
    """Fibre before copper, and within fibre the cheaper one. All three cover a household."""
    found = rank([
        option("DEI", "fibre 1G", "fibre", 1000, "19.90"),
        option("NOVA", "fibre 100", "copper", 100, "21", technology="VECT_VDSL"),
        option("VODAFONE", "fibre 300", "fibre", 300, "24.22"),
    ])
    assert order(found) == ["fibre 1G", "fibre 300", "fibre 100"]
    assert found[0].why == BEST
    assert all(r.enough for r in found)


def test_fibre_beats_a_cheaper_cell() -> None:
    """A cell is shared with the street at seven in the evening and a line is not."""
    found = rank([
        option("OTE", "gigamax", "wireless", 240, "30.00", technology="MOBILE"),
        option("INALAN", "inalan 1G", "fibre", 1000, "34.00"),
    ])
    assert order(found) == ["inalan 1G", "gigamax"]


def test_a_dearer_gigabit_loses_to_a_cheaper_one() -> None:
    """Above the bar the extra speed is a number on a bill, not a difference anyone sees."""
    found = rank([
        option("DEI", "fibre 2.5G", "fibre", 2500, "52.90"),
        option("NOVA", "fibre 300", "fibre", 300, "23"),
    ])
    assert order(found) == ["fibre 300", "fibre 2.5G"]


def test_below_the_bar_speed_decides_not_price() -> None:
    """The choice is no longer which good option but which least bad one."""
    found = rank([
        option("OTE", "adsl 24", "copper", 24, "19.90", technology="ADSL"),
        option("VODAFONE", "vdsl 50", "copper", 50, "26", technology="VDSL"),
    ])
    assert order(found) == ["vdsl 50", "adsl 24"]
    assert found[0].why == FASTEST
    assert found[1].why == SHORT
    assert not any(r.enough for r in found)


def test_a_line_is_preferred_to_a_cell_at_the_same_price() -> None:
    """A cell shares its capacity with the neighbourhood at seven in the evening."""
    found = rank([
        option("OTE", "5g wifi", "wireless", 300, "30.90", technology="FWA_5G"),
        option("OTE", "fibre 500", "fibre", 500, "30.90"),
    ])
    assert order(found) == ["fibre 500", "5g wifi"]


def test_a_dish_ranks_last_among_equals() -> None:
    found = rank([
        option("STARLINK", "starlink", "satellite", 100, "35", hardware=0),
        option("OTE", "5g wifi", "wireless", 100, "35", technology="FWA_5G"),
        option("NOVA", "fibre", "fibre", 100, "35"),
    ])
    assert order(found) == ["fibre", "5g wifi", "starlink"]


def test_the_dish_loses_on_its_hardware_not_its_headline() -> None:
    """35 a month against 35,90 and the dish still loses: 349€ is 14,54 a month of it."""
    found = rank([
        option("STARLINK", "starlink", "satellite", 100, "35", hardware=349),
        option("OTE", "5g wifi", "wireless", 300, "35.90", technology="FWA_5G", hardware=0),
    ])
    assert order(found) == ["5g wifi", "starlink"]


def test_an_unknown_speed_is_never_fast_enough() -> None:
    """Not knowing how fast a wireless link is here is not evidence that it is fast."""
    found = rank([
        option("VODAFONE", "wireless home", "wireless", None, "26.90", technology="FWA"),
        option("OTE", "adsl", "copper", 24, "24", technology="ADSL"),
    ])
    assert order(found) == ["adsl", "wireless home"]
    assert not any(r.enough for r in found)


def test_a_missing_setup_fee_does_not_cost_an_offer_its_place() -> None:
    """The monthly rate is known, so the offer is ranked on it and marked as a floor.

    It used to be dropped below everything priced and labelled "the cost is not known",
    which is three HCN plans — 16, 23 and 29 euro a month, all published — sent to the
    bottom of the page over a setup fee worth about 1.25 a month once it is spread.
    """
    found = rank([
        option("HCN", "sonic", "fibre", 1000, "23", setup=None),
        option("NOVA", "fibre 100", "copper", 100, "21", technology="VECT_VDSL"),
    ])
    # Fibre beats vectoring on steadiness, and both clear the bar, so it leads on merit.
    assert order(found) == ["sonic", "fibre 100"]
    assert found[0].why == FROM
    assert found[0].enough is True
    assert found[0].option.cost.complete is False
    assert found[0].option.cost.total == Decimal("23")


def test_a_fully_published_price_is_not_marked_as_a_floor() -> None:
    found = rank([option("NOVA", "fibre 100", "copper", 100, "21", technology="VECT_VDSL")])
    assert found[0].option.cost.complete is True
    assert found[0].why != FROM


def test_nothing_at_all_ranks_nothing() -> None:
    assert rank([]) == []


def test_the_bar_is_a_judgement_that_can_be_moved() -> None:
    """Someone who works from home may want the gigabit the household does not."""
    options = [
        option("DEI", "fibre 1G", "fibre", 1000, "19.90"),
        option("NOVA", "fibre 100", "copper", 100, "21", technology="VECT_VDSL"),
    ]
    assert rank(options, need=Decimal(500))[0].option.plan == "fibre 1G"
    assert rank(options, need=Decimal(500))[1].enough is False


def metered(gb: int | None, mbps: int, monthly: str) -> Option:
    return Option(
        provider="OTE", provider_name="Telekom", plan=f"gigamax {gb}",
        technology="MOBILE", family="wireless",
        expected_mbps=Decimal(mbps),
        cost=blended(Price(monthly_eur=Decimal(monthly),
                           setup_eur=Decimal(0), hardware_eur=Decimal(0))),
        data_cap_gb=gb,
    )


def test_a_metered_plan_does_not_cover_a_household() -> None:
    """It is fast, it is cheap, and it runs out in the second week."""
    found = rank([metered(9, 240, "24.00"), metered(None, 240, "41.00")])
    assert order(found) == ["gigamax None", "gigamax 9"]
    assert found[0].enough is True
    assert found[1].enough is False


def test_a_generous_cap_still_is_not_a_month() -> None:
    """Seventy gigabytes is a fortnight of one television, not a house."""
    assert rank([metered(70, 300, "36.00")])[0].enough is False
    assert rank([metered(500, 300, "36.00")])[0].enough is True


def test_the_cheapest_metered_plan_never_wins_on_price_alone() -> None:
    """Ranking on cost alone would put a 9GB SIM above every line at the address."""
    found = rank([
        metered(9, 240, "24.00"),
        option("OTE", "5g wifi", "wireless", 240, "35.90", technology="FWA_5G"),
    ])
    assert order(found) == ["5g wifi", "gigamax 9"]


def test_a_plan_is_never_faster_than_it_is_sold_as() -> None:
    """Their 5G router sold at 50 Mbps delivers 50 on a cell that carries 300."""
    from ranking.offer import speed

    assert speed("wireless", Decimal(50), None, None, Decimal(300), None).mbps == Decimal(50)
    assert speed("wireless", Decimal(300), None, None, Decimal(300), None).mbps == Decimal(240)


def test_an_operator_quote_beats_the_advertised_rung() -> None:
    """They guarantee 93 on a plan sold as 100, and 93 is what the line carries."""
    from ranking.offer import speed

    assert speed("copper", Decimal(100), Decimal(100), Decimal(93), None, None).mbps == Decimal(93)


def test_no_equipment_means_no_equipment_to_pay_for() -> None:
    """Zero here is what the catalogue says, not what we assumed it meant."""
    from ranking.offer import owned

    assert owned(None, None) == Decimal(0)
    assert owned("dish", None) is None
    assert owned("dish", Decimal(349)) == Decimal(349)


def test_a_dish_wins_where_nothing_else_reaches() -> None:
    """No line, and a cell filed at ten megabits shared three ways. This is what it is for."""
    found = rank([
        metered(None, 8, "41.00"),
        option("STARLINK", "starlink 200", "satellite", 140, "45", hardware=349),
        option("STARLINK", "starlink 100", "satellite", 70, "35", hardware=349),
    ])
    assert order(found)[0] == "starlink 200"
    assert found[0].enough is True
    assert found[1].enough is False


def test_a_dish_does_not_win_where_a_cell_is_good() -> None:
    """It is the last resort, not a default: 349€ of dish against a router given away."""
    found = rank([
        metered(None, 240, "41.00"),
        option("STARLINK", "starlink 200", "satellite", 140, "45", hardware=349),
    ])
    assert order(found)[0] == "gigamax None"
