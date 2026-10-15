from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml

from publish import fields
from tools.codegen_tiles import PYTHON_OUT, SCHEMA, TYPESCRIPT_OUT, load, python_source

ROOT = Path(__file__).resolve().parent.parent


def test_codegen() -> None:
    done = subprocess.run([sys.executable, "tools/codegen_tiles.py", "--check"], cwd=ROOT, capture_output=True,
                          text=True)
    assert done.returncode == 0, done.stderr

    schema = load()
    python = PYTHON_OUT.read_text(encoding="utf-8")
    typescript = TYPESCRIPT_OUT.read_text(encoding="utf-8")
    for name, layer in schema["layers"].items():
        for field in layer["fields"]:
            assert f'"{field}"' in python, f"{name}.{field} missing from the Python side"
            assert field in typescript, f"{name}.{field} missing from the TypeScript side"

    # rename a field and the check has to fail
    streets = schema["layers"]["streets"]["fields"]
    streets["best_mbps_renamed"] = streets.pop("best_mbps")
    assert "best_mbps_renamed" in python_source(schema)
    assert PYTHON_OUT.read_text(encoding="utf-8") != python_source(schema)


def test_fields() -> None:
    assert "best_mbps" in fields.STREETS_NULLABLE
    assert "readonly best_mbps: Mbps | null;" in TYPESCRIPT_OUT.read_text(encoding="utf-8")
    # a cell only exists because someone tested there
    assert fields.CELLS_NULLABLE == ()

    for code in sorted(fields.STREETS_BY_PROVIDER):
        assert fields.STREETS_BY_PROVIDER[code] in fields.STREETS_FIELDS
    named = list(fields.STREETS_BY_PROVIDER.values())
    assert len(named) == len(set(named))

    schema = yaml.safe_load(SCHEMA.read_text(encoding="utf-8"))
    typescript = TYPESCRIPT_OUT.read_text(encoding="utf-8")
    for layer in schema["layers"].values():
        for field, spec in layer["fields"].items():
            if spec.get("unit") == "mbps":
                assert f"readonly {field}: Mbps" in typescript
