"""Bringing an empty machine up, in the one order that works."""

from __future__ import annotations

from pathlib import Path

from tools.bootstrap import STAGES, Stage, misordered, skipped


def named(name: str) -> Stage:
    return next(stage for stage in STAGES if stage.name == name)


def order() -> list[str]:
    return [stage.name for stage in STAGES]


def test_the_declared_order_satisfies_every_dependency() -> None:
    assert misordered(STAGES) == []


def test_prices_run_before_the_build() -> None:
    """The invisible one. The build only gives a network builder coverage where a tariff for."""
    assert "prices" in named("build").after
    assert order().index("prices") < order().index("build")


def test_nothing_touches_the_database_before_it_exists() -> None:
    assert order()[0] == "database"
    assert order()[1] == "migrate"
    for stage in STAGES:
        if stage.name not in ("database", "migrate"):
            assert "migrate" in stage.after or "migrate" in named(stage.after[0]).after


def test_the_build_comes_last() -> None:
    """Everything else puts rows in raw tables. This is the only thing that reads them all."""
    assert order()[-1] == "build"


def test_an_order_that_does_not_work_is_caught() -> None:
    """The check runs before any stage does, so a bad order costs nothing to discover."""
    first = Stage("first", lambda: 0, "does first")
    second = Stage("second", lambda: 0, "does second", after=("first",))
    assert misordered((first, second)) == []
    assert misordered((second, first)) == ["second runs before first"]


def test_the_real_order_would_be_caught_if_it_were_wrong() -> None:
    """Reversed, the build reports every input it was supposed to wait for."""
    backwards = tuple(reversed(STAGES))
    assert "build runs before prices" in misordered(backwards)


def test_the_scrape_is_optional_and_says_what_is_lost() -> None:
    """It is months of someone's asking and several gigabytes. A clone cannot reproduce it,
    and should be told what it is doing without rather than left to wonder."""
    scrape = named("scrape")
    assert scrape.optional
    assert "326,249" in scrape.missing
    assert "still runs" in scrape.missing


def test_an_absent_optional_input_explains_itself() -> None:
    stage = Stage("x", lambda: 0, "does x", optional=True,
                  missing="nothing here", needs=(Path("/nonexistent/file"),))
    assert skipped(stage) == "nothing here"


def test_an_absent_required_input_is_not_waved_through() -> None:
    stage = Stage("x", lambda: 0, "does x", needs=(Path("/nonexistent/file"),))
    why = skipped(stage)
    assert why is not None
    assert "not found" in why


def test_a_stage_with_everything_it_needs_is_not_skipped() -> None:
    assert skipped(Stage("x", lambda: 0, "does x")) is None
    assert skipped(named("migrate")) is None
