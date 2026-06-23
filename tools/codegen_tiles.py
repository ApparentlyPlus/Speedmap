"""Generate both sides of the tile contract from schema/tiles.yaml.

The field names in a vector tile are an API with no enforcement: a renderer asking for a
field the builder stopped writing gets undefined, paints its fallback, and reports nothing.
Generating both sides from one file turns that silence into a failed build.

Run it with --check in CI and it asserts the files on disk are what the schema says, which
is the half that matters: generating is easy to remember while editing the schema and easy
to forget while reviewing a diff.
"""

from __future__ import annotations

import argparse
import pathlib
import sys
import textwrap
from typing import Any

import yaml

# Both generated files are linted like the rest, so prose has to be wrapped here rather
# than emitted as one long line and argued about later.
WIDTH = 92

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCHEMA = ROOT / "schema" / "tiles.yaml"
PYTHON_OUT = ROOT / "publish" / "fields.py"
TYPESCRIPT_OUT = ROOT / "web" / "src" / "map" / "tiles.ts"

BANNER = "Generated from schema/tiles.yaml. Do not edit; edit the schema and regenerate."

# A unit in the schema becomes a unit in the type, because several prototype bugs were a
# number in the right shape and the wrong unit, and nothing in the code objected.
BRANDED = {"mbps": "Mbps"}

PYTHON_TYPES = {"integer": "int", "number": "float", "string": "str"}
TYPESCRIPT_TYPES = {"integer": "number", "number": "number", "string": "string"}


def wrapped(text: str, prefix: str) -> list[str]:
    """A description broken to the line length, each line carrying its own comment marker."""
    flat = " ".join(str(text).split())
    return [prefix + line for line in textwrap.wrap(flat, WIDTH - len(prefix))]


def load() -> dict[str, Any]:
    parsed: dict[str, Any] = yaml.safe_load(SCHEMA.read_text(encoding="utf-8"))
    return parsed


def python_source(schema: dict[str, Any]) -> str:
    lines = [f'"""{BANNER}"""', "", "from __future__ import annotations", "", "from typing import Final", ""]
    lines += [f"VERSION: Final = {schema['version']}", ""]

    for name, layer in schema["layers"].items():
        upper = name.upper()
        fields = layer["fields"]
        lines += wrapped(str(layer["description"]), "# ")
        lines += [f'{upper}_LAYER: Final = "{name}"']
        lines += [f"{upper}_FIELDS: Final = ("]
        lines += [f'    "{field}",' for field in fields]
        lines += [")", ""]

        by_provider = {
            str(spec["provider"]): field
            for field, spec in fields.items()
            if "provider" in spec
        }
        if by_provider:
            lines += [
                "# The operator each per-operator field belongs to. The builder pivots the",
                "# provider table through this, so an operator with no field here is not",
                "# written rather than written under a guessed name.",
                f"{upper}_BY_PROVIDER: Final[dict[str, str]] = {{",
            ]
            lines += [f'    "{code}": "{field}",' for code, field in by_provider.items()]
            lines += ["}", ""]

        nullable = [field for field, spec in fields.items() if spec.get("nullable")]
        lines += [f"{upper}_NULLABLE: Final = ("]
        lines += [f'    "{field}",' for field in nullable]
        lines += [")", ""]

    lines += ["LAYERS: Final = (", *[f'    "{name}",' for name in schema["layers"]], ")", ""]
    return "\n".join(lines)


def typescript_source(schema: dict[str, Any]) -> str:
    lines = [f"/** {BANNER} */", "", 'import type { Mbps } from "../tokens";', ""]
    lines += [f"export const VERSION = {schema['version']} as const;", ""]

    for name, layer in schema["layers"].items():
        fields = layer["fields"]
        typed = name[:1].upper() + name[1:].rstrip("s")
        lines += ["/**", *wrapped(str(layer["description"]), " * "), " */"]
        lines += [f"export type {typed} = {{"]
        for field, spec in fields.items():
            unit = BRANDED.get(str(spec.get("unit", "")))
            base = unit if unit else TYPESCRIPT_TYPES[str(spec["type"])]
            hint = " | null" if spec.get("nullable") else ""
            note = spec.get("description")
            if note:
                broken = wrapped(str(note), "   * ")
                lines += (
                    [f"  /** {' '.join(str(note).split())} */"]
                    if len(broken) == 1
                    else ["  /**", *broken, "   */"]
                )
            lines += [f"  readonly {field}: {base}{hint};"]
        lines += ["};", ""]

        lines += [f'export const {name.upper()}_LAYER = "{name}" as const;']
        lines += [f"export const {name.upper()}_FIELDS = ["]
        lines += [f'  "{field}",' for field in fields]
        lines += ["] as const;", ""]

        by_provider = {
            str(spec["provider"]): field
            for field, spec in fields.items()
            if "provider" in spec
        }
        if by_provider:
            lines += [
                "/** The field each operator's speed is written under, for the filter. */",
                f"export const {name.upper()}_BY_PROVIDER: Readonly<",
                f"  Record<string, keyof {typed}>",
                "> = {",
            ]
            lines += [f'  {code}: "{field}",' for code, field in by_provider.items()]
            lines += ["};", ""]

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true",
        help="fail if the generated files are not what the schema says",
    )
    asked = parser.parse_args()

    schema = load()
    wanted = {PYTHON_OUT: python_source(schema), TYPESCRIPT_OUT: typescript_source(schema)}

    stale = [
        path for path, body in wanted.items()
        if not path.exists() or path.read_text(encoding="utf-8") != body
    ]
    if asked.check:
        for path in stale:
            print(f"stale: {path.relative_to(ROOT)}", file=sys.stderr)
        if stale:
            print("run tools/codegen_tiles.py to regenerate", file=sys.stderr)
        return 1 if stale else 0

    for path, body in wanted.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        print(f"wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
