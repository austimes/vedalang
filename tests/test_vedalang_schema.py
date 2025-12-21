import json
import yaml
from pathlib import Path
import jsonschema
import pytest

PROJECT_ROOT = Path(__file__).parent.parent
SCHEMA_PATH = PROJECT_ROOT / "vedalang" / "schema" / "vedalang.schema.json"
EXAMPLES_DIR = PROJECT_ROOT / "vedalang" / "examples"

def load_schema():
    with open(SCHEMA_PATH) as f:
        return json.load(f)

def test_mini_plant_validates():
    """The mini_plant example should pass validation."""
    schema = load_schema()
    with open(EXAMPLES_DIR / "mini_plant.veda.yaml") as f:
        data = yaml.safe_load(f)
    jsonschema.validate(data, schema)

def test_missing_model_rejected():
    """Document without 'model' key should be rejected."""
    schema = load_schema()
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"foo": "bar"}, schema)

def test_missing_required_fields_rejected():
    """Model missing required fields should be rejected."""
    schema = load_schema()
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"model": {"name": "Test"}}, schema)

def test_invalid_commodity_type_rejected():
    """Invalid commodity type enum should be rejected."""
    schema = load_schema()
    data = {
        "model": {
            "name": "Test",
            "regions": ["R1"],
            "commodities": [{"name": "X", "type": "invalid_type"}],
            "processes": []
        }
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(data, schema)

def test_efficiency_range():
    """Efficiency must be between 0 and 1."""
    schema = load_schema()
    data = {
        "model": {
            "name": "Test",
            "regions": ["R1"],
            "commodities": [],
            "processes": [{"name": "P1", "sets": ["ELE"], "efficiency": 1.5}]
        }
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(data, schema)
