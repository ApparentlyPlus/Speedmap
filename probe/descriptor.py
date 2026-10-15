"""Each operator's checker as described in adapters.yaml, their APIs change too often for code."""

from __future__ import annotations

from decimal import Decimal
from functools import cache
from pathlib import Path
from typing import Any

import yaml

ADAPTERS = Path(__file__).parent / "adapters.yaml"


@cache
def descriptors(path: Path = ADAPTERS) -> dict[str, dict[str, Any]]:
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    return {str(code): dict(entry) for code, entry in doc.items()}


class Descriptor:
    def __init__(self, code: str, path: Path = ADAPTERS) -> None:
        self.code = code
        self.held = descriptors(path)[code]

    def text(self, key: str) -> str:
        return str(self.held[key])

    def url(self, key: str) -> str:
        return f"{self.text('base')}{self.text(key)}"

    def mapping(self, key: str) -> dict[str, str]:
        return {str(k): str(v) for k, v in self.held.get(key, {}).items()}

    def rungs(self) -> tuple[tuple[Decimal, str], ...]:
        """(speed, technology), fastest first."""
        return tuple((Decimal(str(lo)), str(tech)) for lo, tech in self.held.get("rungs", ()))

    def payload(self, key: str) -> dict[str, Any]:
        return dict(self.held.get(key, {}))
