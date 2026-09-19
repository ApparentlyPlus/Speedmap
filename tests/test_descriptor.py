"""The parts of an adapter that are data, and stay data."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import psycopg
import pytest
from psycopg.rows import TupleRow

from probe.descriptor import ADAPTERS, Descriptor, descriptors

OPERATORS = sorted(descriptors())

# What each module reads out of its own entry. A key renamed in the file and not here is a
# crash on the first probe of the day. This makes it a failing test instead.
READS = {
    "OTE": ("base", "warm", "availability", "form", "constants", "inconclusive",
            "prefecture_prefix", "municipality_prefix", "rungs", "headers"),
    "VODAFONE": ("base", "warm", "qualify", "proxy", "process", "retail_party",
                 "technology", "bare", "headers"),
    "NOVA": ("base", "warm", "streets", "eligibility", "preselect", "rungs",
             "prefecture_prefix", "municipality_prefix", "headers"),
}


@pytest.mark.parametrize("code", OPERATORS)
def test_an_operator_has_everything_its_adapter_reads(code: str) -> None:
    held = descriptors()[code]
    for key in READS[code]:
        assert key in held, f"{code} is missing {key}"


@pytest.mark.parametrize("code", OPERATORS)
def test_a_path_joins_onto_the_base(code: str) -> None:
    """A domain moving should be one line, which is the whole reason these are here."""
    spec = Descriptor(code)
    assert spec.url("warm").startswith(spec.text("base"))


@pytest.mark.parametrize("code", OPERATORS)
def test_every_base_is_a_url(code: str) -> None:
    assert Descriptor(code).text("base").startswith("https://")


def test_rungs_run_fastest_first_and_reach_the_bottom() -> None:
    """They are read in order and the first match wins, so an unsorted list silently
    returns the wrong technology rather than failing."""
    for code in ("OTE", "NOVA"):
        rungs = Descriptor(code).rungs()
        assert rungs
        floors = [floor for floor, _ in rungs]
        assert floors == sorted(floors, reverse=True), code
        assert floors[-1] == Decimal(0), code


def test_every_technology_named_is_one_we_have(db: psycopg.Connection[TupleRow]) -> None:
    """A code invented in the file would reach the ranker as a plan on no line at all."""
    known = {
        str(code) for (code,) in db.execute("select code from technology").fetchall()
    }
    for code in OPERATORS:
        spec = Descriptor(code)
        named = set(spec.mapping("technology").values()) | set(spec.mapping("bare").values())
        named |= {technology for _, technology in spec.rungs()}
        assert named <= known, f"{code} names {named - known}"


def test_the_file_lives_with_the_code_that_reads_it() -> None:
    assert ADAPTERS.exists()
    assert ADAPTERS.parent == Path(__file__).resolve().parent.parent / "probe"


def test_reading_it_twice_reads_it_once() -> None:
    """Every adapter builds its descriptor at import, and there are three of them."""
    assert descriptors() is descriptors()
