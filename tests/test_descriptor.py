from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import psycopg
from psycopg.rows import TupleRow

from probe.descriptor import ADAPTERS, Descriptor, descriptors

OPERATORS = sorted(descriptors())

# what each adapter reads, so a renamed key fails here and not on the first probe
READS = {
    "TELEKOM": ("base", "warm", "availability", "form", "constants", "inconclusive",
                "prefecture_prefix", "municipality_prefix", "rungs", "headers"),
    "VODAFONE": ("base", "warm", "qualify", "proxy", "process", "retail_party", "technology", "bare", "headers"),
    "NOVA": ("base", "warm", "streets", "eligibility", "preselect", "rungs", "prefecture_prefix",
             "municipality_prefix", "headers"),
}


def test_descriptors() -> None:
    for code in OPERATORS:
        held = descriptors()[code]
        for key in READS[code]:
            assert key in held, f"{code} is missing {key}"
        spec = Descriptor(code)
        assert spec.url("warm").startswith(spec.text("base"))
        assert Descriptor(code).text("base").startswith("https://")

    assert ADAPTERS.exists()
    assert ADAPTERS.parent == Path(__file__).resolve().parent.parent / "probe"
    assert descriptors() is descriptors()


def test_rungs() -> None:
    # first match wins, unsorted would quietly pick the wrong technology
    for code in ("TELEKOM", "NOVA"):
        rungs = Descriptor(code).rungs()
        assert rungs
        floors = [lo for lo, _ in rungs]
        assert floors == sorted(floors, reverse=True), code
        assert floors[-1] == Decimal(0), code


def test_technologies(db: psycopg.Connection[TupleRow]) -> None:
    known = {str(code) for (code,) in db.execute("select code from technology").fetchall()}
    for code in OPERATORS:
        spec = Descriptor(code)
        named = set(spec.mapping("technology").values()) | set(spec.mapping("bare").values())
        named |= {tech for _, tech in spec.rungs()}
        assert named <= known, f"{code} names {named - known}"
