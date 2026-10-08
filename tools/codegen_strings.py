"""Generate the site's text from web/src/strings.toml.

The TOML is the one place the wording lives, so it can be edited without touching code. This
turns it into typed TypeScript, which means a key the code asks for and the file doesn't have
fails the typecheck instead of showing a blank.

It also refuses a file the two languages disagree on: a key in one and not the other, or a
sentence that dropped a {placeholder} in translation and would print the brace.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import tomllib
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parent.parent
SOURCE = ROOT / "web" / "src" / "strings.toml"
OUT = ROOT / "web" / "src" / "strings.ts"

LANGUAGES = ("el", "en")
BANNER = "Generated from strings.toml. Edit the TOML and run `make strings`, never this file."

PLACEHOLDER = re.compile(r"\{(\w+)\}")
IDENTIFIER = re.compile(r"^[A-Za-z_$][\w$]*$")


def load() -> dict[str, Any]:
    return tomllib.loads(SOURCE.read_text(encoding="utf-8"))


def disagreements(el: dict[str, Any], en: dict[str, Any], at: str = "") -> list[str]:
    """Every way the two languages differ in shape, as a line each."""
    found = []
    for key in sorted(set(el) | set(en)):
        where = f"{at}{key}"
        if key not in en:
            found.append(f"{where}: in el, missing from en")
        elif key not in el:
            found.append(f"{where}: in en, missing from el")
        elif isinstance(el[key], dict) != isinstance(en[key], dict):
            found.append(f"{where}: a group in one language and a sentence in the other")
        elif isinstance(el[key], dict):
            found += disagreements(el[key], en[key], f"{where}.")
        elif set(PLACEHOLDER.findall(el[key])) != set(PLACEHOLDER.findall(en[key])):
            found.append(f"{where}: el fills {sorted(set(PLACEHOLDER.findall(el[key])))}, "
                         f"en fills {sorted(set(PLACEHOLDER.findall(en[key])))}")
    return found


def key(name: str) -> str:
    return name if IDENTIFIER.match(name) else json.dumps(name, ensure_ascii=False)


def typed(table: dict[str, Any]) -> list[str]:
    """The Strings type. A group is an open record, since the code looks some of them up by a
    value that comes from the data (a technology code, a family)."""
    lines = ["export type Strings = {"]
    for name, value in table.items():
        kind = "Readonly<Record<string, string>>" if isinstance(value, dict) else "string"
        lines.append(f"  readonly {key(name)}: {kind};")
    return [*lines, "};"]


def literal(value: Any, indent: str) -> str:
    if not isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    inner = indent + "  "
    body = "".join(f"{inner}{key(k)}: {literal(v, inner)},\n" for k, v in value.items())
    return "{\n" + body + indent + "}"


def source(strings: dict[str, Any]) -> str:
    lines = [f"/** {BANNER} */", "", *typed(strings["el"]), ""]
    for language in LANGUAGES:
        lines += [f"export const {language}: Strings = {literal(strings[language], '')};", ""]
    lines += [
        "/** Each operator's name as the site shows it, the same in both languages. */",
        f"export const OPERATOR_NAMES: Readonly<Record<string, string>> = {literal(strings['operators'], '')};",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if strings.ts is not what the TOML says")
    asked = parser.parse_args()

    try:
        strings = load()
    except tomllib.TOMLDecodeError as error:
        print(f"{SOURCE.relative_to(ROOT)}: {error}", file=sys.stderr)
        return 1
    missing = [table for table in (*LANGUAGES, "operators") if table not in strings]
    if missing:
        print(f"{SOURCE.relative_to(ROOT)}: no [{'], ['.join(missing)}] table", file=sys.stderr)
        return 1
    problems = disagreements(strings["el"], strings["en"])
    if problems:
        print(f"{SOURCE.relative_to(ROOT)}: Greek and English disagree:", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1

    body = source(strings)
    if asked.check:
        if not OUT.exists() or OUT.read_text(encoding="utf-8") != body:
            print(f"stale: {OUT.relative_to(ROOT)}\nrun `make strings` to regenerate", file=sys.stderr)
            return 1
        return 0
    OUT.write_text(body, encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
