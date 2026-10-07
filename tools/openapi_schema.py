"""Write the OpenAPI document the frontend types are generated from.

schema/openapi.json is the contract between the API and the renderer.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "schema" / "openapi.json"


def document() -> str:
    # imported here: the module opens a connection pool, and printing the schema shouldn't
    # need a running database
    from api.main import app

    schema: dict[str, Any] = app.openapi()
    return json.dumps(schema, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if the file does not match the server")
    asked = parser.parse_args()

    wanted = document()
    if asked.check:
        held = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if held == wanted:
            return 0
        print(f"stale: {OUT.relative_to(ROOT)}", file=sys.stderr)
        print("run tools/openapi_schema.py, then web/npm run api:types", file=sys.stderr)
        return 1

    OUT.write_text(wanted, encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
