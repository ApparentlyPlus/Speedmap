"""Write schema/openapi.json, which the frontend types are generated from."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "schema" / "openapi.json"

# Keywords that describe or validate a value without changing its shape on the wire. FastAPI
# and pydantic render these differently from release to release (pydantic 2.14 dropped the
# decimal pattern), so --check ignores them and only fails on a change a client would notice.
PROSE = frozenset({"title", "description", "summary"})
LIMITS = frozenset({"pattern", "minLength", "maxLength", "minimum", "maximum", "exclusiveMinimum",
                    "exclusiveMaximum", "multipleOf", "minItems", "maxItems"})


def document() -> dict[str, Any]:
    # late, api.main opens a pool
    from api.main import app

    schema: dict[str, Any] = app.openapi()
    return schema


def contract(node: Any) -> Any:
    """The document minus PROSE and LIMITS. Keys are only dropped when the value has the
    keyword's type, so a field that happens to be called `title` survives."""
    if isinstance(node, list):
        return [contract(x) for x in node]
    if not isinstance(node, dict):
        return node
    out = {}
    for k, v in node.items():
        if k in PROSE and isinstance(v, str):
            continue
        if k in LIMITS and isinstance(v, str | int | float) and not isinstance(v, bool):
            continue
        out[k] = contract(v)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if the server's contract differs from the file")
    args = parser.parse_args()

    wanted = document()
    if args.check:
        held = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
        if contract(held) == contract(wanted):
            return 0
        print(f"stale: {OUT.relative_to(ROOT)}", file=sys.stderr)
        print("run make codegen", file=sys.stderr)
        return 1

    OUT.write_text(json.dumps(wanted, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
