"""Tests for VedaLang compiler."""

import json
from pathlib import Path

import jsonschema
import pytest

from vedalang.compiler import compile_vedalang_to_tableir, load_vedalang

PROJECT_ROOT = Path(__file__).parent.parent
EXAMPLES_DIR = PROJECT_ROOT / "vedalang" / "examples"
SCHEMA_DIR = PROJECT_ROOT / "vedalang" / "schema"


def test_compile_mini_plant():
    """Compile mini_plant.veda.yaml to TableIR."""
    source = load_vedalang(EXAMPLES_DIR / "mini_plant.veda.yaml")
    tableir = compile_vedalang_to_tableir(source)

    # Should have files
    assert "files" in tableir
    assert len(tableir["files"]) >= 1


def test_output_validates_against_tableir_schema():
    """Compiler output must be valid TableIR."""
    source = load_vedalang(EXAMPLES_DIR / "mini_plant.veda.yaml")
    tableir = compile_vedalang_to_tableir(source)

    with open(SCHEMA_DIR / "tableir.schema.json") as f:
        schema = json.load(f)

    # Should not raise
    jsonschema.validate(tableir, schema)


def test_commodities_become_fi_comm():
    """Commodities should appear in ~FI_COMM table."""
    source = load_vedalang(EXAMPLES_DIR / "mini_plant.veda.yaml")
    tableir = compile_vedalang_to_tableir(source)

    # Find ~FI_COMM table
    comm_tables = []
    for f in tableir["files"]:
        for s in f["sheets"]:
            for t in s["tables"]:
                if t["tag"] == "~FI_COMM":
                    comm_tables.append(t)

    assert len(comm_tables) >= 1
    comm_names = [r.get("commname") for r in comm_tables[0]["rows"]]
    assert "ELC" in comm_names
    assert "NG" in comm_names


def test_processes_become_fi_process():
    """Processes should appear in ~FI_PROCESS table."""
    source = load_vedalang(EXAMPLES_DIR / "mini_plant.veda.yaml")
    tableir = compile_vedalang_to_tableir(source)

    # Find ~FI_PROCESS table
    proc_tables = []
    for f in tableir["files"]:
        for s in f["sheets"]:
            for t in s["tables"]:
                if t["tag"] == "~FI_PROCESS":
                    proc_tables.append(t)

    assert len(proc_tables) >= 1
    tech_names = [r.get("techname") for r in proc_tables[0]["rows"]]
    assert "PP_CCGT" in tech_names


def test_invalid_vedalang_rejected():
    """Invalid VedaLang should raise ValidationError."""
    invalid = {"not_a_model": True}
    with pytest.raises(jsonschema.ValidationError):
        compile_vedalang_to_tableir(invalid)
