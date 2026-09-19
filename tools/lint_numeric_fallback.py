# !/usr/bin/env python3.
"""Forbid substituting a plausible number for a missing one.

The Python spellings of that mistake are: speed = row.get("maxdown") or 0 # SM001 invents 0
Mbps premises = prempass or 1 # SM001 invents a dwelling speed = row.get("maxdown".
"""

from __future__ import annotations

import ast
import sys
import tokenize
from dataclasses import dataclass
from pathlib import Path

SUPPRESS = "allow-fallback:"

EXCLUDE_DIRS = frozenset(
    {".git", ".venv", "node_modules", "__pycache__", ".mypy_cache", ".ruff_cache"}
)


@dataclass(frozen=True)
class Finding:
    path: Path
    line: int
    col: int
    code: str
    message: str


def _is_number(node: ast.expr) -> bool:
    """True for a numeric literal, including a negated one."""
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.UAdd | ast.USub):
        return _is_number(node.operand)
    return (
        isinstance(node, ast.Constant)
        and isinstance(node.value, int | float | complex)
        and not isinstance(node.value, bool)
    )


def _unparse(node: ast.expr) -> str:
    text = ast.unparse(node)
    return text if len(text) <= 60 else text[:57] + "..."


class _Visitor(ast.NodeVisitor):
    def __init__(self, path: Path) -> None:
        self.path = path
        self.findings: list[Finding] = []

    def visit_BoolOp(self, node: ast.BoolOp) -> None:
        if isinstance(node.op, ast.Or):
            # values[0] is the tested expression and anything after it is a default.
            for value in node.values[1:]:
                if _is_number(value):
                    self.findings.append(
                        Finding(
                            self.path,
                            value.lineno,
                            value.col_offset,
                            "SM001",
                            f"`or {_unparse(value)}` invents a number for a missing one. "
                            f"Keep it None and let the caller render 'not filed'.",
                        )
                    )
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        # d.get(key, 0) and getattr(o, name.
        name: str | None = None
        default: ast.expr | None = None
        if isinstance(node.func, ast.Attribute) and node.func.attr == "get" and len(node.args) == 2:
            name, default = "dict.get", node.args[1]
        elif isinstance(node.func, ast.Name) and node.func.id == "getattr" and len(node.args) == 3:
            name, default = "getattr", node.args[2]

        if name is not None and default is not None and _is_number(default):
            self.findings.append(
                Finding(
                    self.path,
                    default.lineno,
                    default.col_offset,
                    "SM002",
                    f"`{name}(..., {_unparse(default)})` invents a number for a missing key. "
                    f"Drop the default so it returns None.",
                )
            )
        self.generic_visit(node)


def _suppressed_lines(source: str) -> set[int]:
    """Lines carrying a `# allow-fallback: <reason>` comment with a real reason."""
    suppressed: set[int] = set()
    try:
        tokens = tokenize.generate_tokens(iter(source.splitlines(keepends=True)).__next__)
        for token in tokens:
            if token.type is tokenize.COMMENT and SUPPRESS in token.string:
                reason = token.string.split(SUPPRESS, 1)[1].strip()
                if reason:
                    suppressed.add(token.start[0])
    except (tokenize.TokenError, IndentationError):
        pass
    return suppressed


def check_source(source: str, path: Path) -> list[Finding]:
    tree = ast.parse(source, filename=str(path))
    visitor = _Visitor(path)
    visitor.visit(tree)
    suppressed = _suppressed_lines(source)
    return [f for f in visitor.findings if f.line not in suppressed]


def _iter_python_files(roots: list[Path]) -> list[Path]:
    files: list[Path] = []
    for root in roots:
        if root.is_file():
            files.append(root)
            continue
        for path in sorted(root.rglob("*.py")):
            if EXCLUDE_DIRS.isdisjoint(path.parts):
                files.append(path)
    return files


def main(argv: list[str]) -> int:
    roots = [Path(a) for a in argv] or [Path()]
    findings: list[Finding] = []
    for path in _iter_python_files(roots):
        source = path.read_text(encoding="utf-8")
        try:
            findings.extend(check_source(source, path))
        except SyntaxError as exc:
            print(f"{path}: could not parse: {exc}")
            return 2

    for f in findings:
        print(f"{f.path}:{f.line}:{f.col + 1}: {f.code} {f.message}")

    if findings:
        n = len(findings)
        print(f"\n{n} numeric fallback{'s' if n != 1 else ''}. Never substitute a value for a")
        print("missing one. Add `# allow-fallback: <reason>` if it is genuinely a default.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
