"""Noticing that a checker has rotted."""

from __future__ import annotations

from pathlib import Path

from probe.adapter import Offer, Probed
from probe.canary import CANARIES, Canary, judge, load
from probe.run import Reply

WATCHED = Canary(
    name="athens", why="fiber for years", municipality="ΔΗΜΟΣ ΑΘΗΝΑΙΩΝ",
    street="ΑΧΑΡΝΩΝ", street_no="100", expect="offers",
)


def answered(*offers: Offer, serviceable: bool = True, conclusive: bool = True) -> Reply:
    return Reply("TELEKOM", Probed(serviceable=serviceable, offers=offers, conclusive=conclusive))


def test_offers_where_there_are_offers_is_a_pass() -> None:
    assert judge(WATCHED, answered(Offer(technology="FTTH"))).passed


def test_no_offers_on_a_street_that_has_them_is_the_failure_this_is_for() -> None:
    """A 200, a page, and nothing in it. Indistinguishable from a country with no broadband
    unless something already knows what the answer should be."""
    verdict = judge(WATCHED, answered())
    assert not verdict.passed
    assert "no offers where there are some" in verdict.detail


def test_an_unreachable_checker_fails_the_canary() -> None:
    verdict = judge(WATCHED, Reply("TELEKOM", None, error="timed out"))
    assert not verdict.passed
    assert "unreachable" in verdict.detail


def test_being_told_to_investigate_fails_it_too() -> None:
    """Neither yes nor no isn't an answer, and a canary asks whether it can answer at all."""
    assert not judge(WATCHED, answered(conclusive=False, serviceable=False)).passed


def test_a_refusal_canary_fails_when_offers_appear() -> None:
    """The other direction: somewhere that should have nothing suddenly having something is
    equally a sign that the parser is reading a different page than it thinks."""
    nowhere = Canary(name="nowhere", why="no service", municipality="X", street="Y",
                     street_no="1", expect="refusal")
    assert judge(nowhere, answered(serviceable=False)).passed
    assert not judge(nowhere, answered(Offer(technology="FTTH"))).passed


def test_the_shipped_canaries_are_usable() -> None:
    canaries = load(CANARIES)
    assert canaries
    for canary in canaries:
        assert canary.expect in ("offers", "refusal")
        assert canary.why, canary.name
        assert canary.street == canary.street.upper()


def test_a_canary_is_pinned_to_a_real_address() -> None:
    """A canary pointed at an address we don't hold reports our gap, which says nothing about
    the adapter. Τζελίλη 40 exists, is served, and isn't in the index: the scan stopped at 1."""
    lagkadas = next(c for c in load(CANARIES) if c.name == "lagkadas-copper")
    assert lagkadas.street_no == "1"


def test_the_file_lives_with_the_code_that_reads_it() -> None:
    assert CANARIES.exists()
    assert CANARIES.parent == Path(__file__).resolve().parent.parent / "probe"
