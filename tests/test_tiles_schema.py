"""The tile contract: both sides generated from one file, and kept that way.

A vector tile field name is an API with no enforcement.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from publish import fields
from tools.codegen_tiles import PYTHON_OUT, SCHEMA, TYPESCRIPT_OUT, load, python_source

ROOT = Path(__file__).resolve().parent.parent


def test_the_generated_files_match_the_schema() -> None:
    """The half that matters: regenerating is easy to remember while editing the schema and
    easy to forget while reviewing a diff."""
    done = subprocess.run(
        [sys.executable, "tools/codegen_tiles.py", "--check"],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert done.returncode == 0, done.stderr


def test_every_layer_reaches_both_sides() -> None:
    schema = load()
    python = PYTHON_OUT.read_text(encoding="utf-8")
    typescript = TYPESCRIPT_OUT.read_text(encoding="utf-8")
    for name, layer in schema["layers"].items():
        for field in layer["fields"]:
            assert f'"{field}"' in python, f"{name}.{field} missing from the Python side"
            assert field in typescript, f"{name}.{field} missing from the TypeScript side"


def test_a_renamed_field_fails_the_check(tmp_path: Path) -> None:
    """The whole point. Rename one and the build stops rather than the map going quiet."""
    schema = load()
    schema["layers"]["streets"]["fields"]["best_mbps_renamed"] = schema["layers"][
        "streets"
    ]["fields"].pop("best_mbps")
    assert "best_mbps_renamed" in python_source(schema)
    assert PYTHON_OUT.read_text(encoding="utf-8") != python_source(schema)


def test_a_nullable_field_says_so_on_both_sides() -> None:
    """A missing number and a zero look identical inside a paint expression, and the
    difference between them is the one the whole ranking rests on."""
    assert "best_mbps" in fields.STREETS_NULLABLE
    assert "readonly best_mbps: Mbps | null;" in TYPESCRIPT_OUT.read_text(encoding="utf-8")


def test_a_measured_field_is_never_nullable() -> None:
    """A cell exists because somebody tested there, so its speed is not an open question."""
    assert fields.CELLS_NULLABLE == ()


@pytest.mark.parametrize("code", sorted(fields.STREETS_BY_PROVIDER))
def test_every_operator_field_is_declared_in_the_layer(code: str) -> None:
    assert fields.STREETS_BY_PROVIDER[code] in fields.STREETS_FIELDS


def test_operator_fields_are_not_shared() -> None:
    """Two operators writing the same field is one operator's speed under both names."""
    named = list(fields.STREETS_BY_PROVIDER.values())
    assert len(named) == len(set(named))


def test_the_units_are_carried_into_the_types() -> None:
    """Several prototype bugs were a number of the right shape in the wrong unit."""
    schema = yaml.safe_load(SCHEMA.read_text(encoding="utf-8"))
    typescript = TYPESCRIPT_OUT.read_text(encoding="utf-8")
    for layer in schema["layers"].values():
        for field, spec in layer["fields"].items():
            if spec.get("unit") == "mbps":
                assert f"readonly {field}: Mbps" in typescript
