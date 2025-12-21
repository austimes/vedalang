import json
from pathlib import Path

import jsonschema
import pytest

PROJECT_ROOT = Path(__file__).parent.parent


@pytest.mark.skipif(
    not (PROJECT_ROOT / "output/diagnostics.json").exists(),
    reason="output/diagnostics.json not found",
)
def test_diagnostics_schema():
    """Validate output/diagnostics.json against its schema."""
    schema_path = PROJECT_ROOT / "vedalang/schema/diagnostics.schema.json"
    data_path = PROJECT_ROOT / "output/diagnostics.json"

    with open(schema_path) as f:
        schema = json.load(f)
    with open(data_path) as f:
        data = json.load(f)

    jsonschema.validate(data, schema)


@pytest.mark.skipif(
    not (PROJECT_ROOT / "output/manifest.json").exists(),
    reason="output/manifest.json not found",
)
def test_manifest_schema():
    """Validate output/manifest.json against its schema."""
    schema_path = PROJECT_ROOT / "vedalang/schema/manifest.schema.json"
    data_path = PROJECT_ROOT / "output/manifest.json"

    with open(schema_path) as f:
        schema = json.load(f)
    with open(data_path) as f:
        data = json.load(f)

    jsonschema.validate(data, schema)
