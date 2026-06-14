"""What each operator's checker looks like, read at runtime rather than compiled in.

You cannot make a third party's private API stable. One of these domains vanished and
another went quiet inside a year, and the answer is not better scraping: it is that the
parts which change when a site is redesigned should be data, so repairing them is an edit
and a restart rather than a code change and a deploy.

What stays in code is parsing. A table whose header row is not a measurement cannot be
expressed here, and pretending otherwise would put the fragile half in a format with no
tests over it.
"""

from __future__ import annotations

from decimal import Decimal
from functools import cache
from pathlib import Path
from typing import Any

import yaml

ADAPTERS = Path(__file__).parent / "adapters.yaml"


@cache
def descriptors(path: Path = ADAPTERS) -> dict[str, dict[str, Any]]:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    return {str(code): dict(entry) for code, entry in document.items()}


class Descriptor:
    """One operator's, with the reads it needs typed at the point of use."""

    def __init__(self, code: str, path: Path = ADAPTERS) -> None:
        self.code = code
        self.held = descriptors(path)[code]

    def text(self, key: str) -> str:
        return str(self.held[key])

    def url(self, key: str) -> str:
        """A path joined to the operator's base, so a domain move is one line."""
        return f"{self.text('base')}{self.text(key)}"

    def mapping(self, key: str) -> dict[str, str]:
        return {str(k): str(v) for k, v in self.held.get(key, {}).items()}

    def rungs(self) -> tuple[tuple[Decimal, str], ...]:
        """Speed to technology, fastest first, as the operator's own codes imply it."""
        return tuple(
            (Decimal(str(floor)), str(technology))
            for floor, technology in self.held.get("rungs", ())
        )

    def payload(self, key: str) -> dict[str, Any]:
        return dict(self.held.get(key, {}))
