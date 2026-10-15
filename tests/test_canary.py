from __future__ import annotations

from pathlib import Path

from probe.adapter import Offer, Probed
from probe.canary import CANARIES, Canary, judge, load
from probe.run import Reply

ATHENS = Canary(name="athens", why="fiber for years", municipality="ΔΗΜΟΣ ΑΘΗΝΑΙΩΝ", street="ΑΧΑΡΝΩΝ",
                street_no="100", expect="offers")


def _reply(*offers: Offer, serviceable: bool = True, conclusive: bool = True) -> Reply:
    return Reply("TELEKOM", Probed(serviceable=serviceable, offers=offers, conclusive=conclusive))


def test_judge() -> None:
    assert judge(ATHENS, _reply(Offer(technology="FTTH"))).passed

    # the case it exists for, a 200 with nothing in it
    v = judge(ATHENS, _reply())
    assert not v.passed
    assert "no offers where there are some" in v.detail

    v = judge(ATHENS, Reply("TELEKOM", None, error="timed out"))
    assert not v.passed
    assert "unreachable" in v.detail

    assert not judge(ATHENS, _reply(conclusive=False, serviceable=False)).passed

    nowhere = Canary(name="nowhere", why="no service", municipality="X", street="Y", street_no="1", expect="refusal")
    assert judge(nowhere, _reply(serviceable=False)).passed
    assert not judge(nowhere, _reply(Offer(technology="FTTH"))).passed


def test_canaries() -> None:
    canaries = load(CANARIES)
    assert canaries
    for c in canaries:
        assert c.expect in ("offers", "refusal")
        assert c.why, c.name
        assert c.street == c.street.upper()

    # Τζελίλη 40 is served but not indexed, the scan stopped at 1
    lagkadas = next(c for c in load(CANARIES) if c.name == "lagkadas-copper")
    assert lagkadas.street_no == "1"

    assert CANARIES.exists()
    assert CANARIES.parent == Path(__file__).resolve().parent.parent / "probe"
