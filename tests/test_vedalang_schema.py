import json
from pathlib import Path

import jsonschema
import pytest
import yaml

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


def test_timeslices_validates():
    """Timeslice structure should validate against schema."""
    schema = load_schema()
    data = {
        "model": {
            "name": "TimesliceTest",
            "regions": ["R1"],
            "timeslices": {
                "season": [
                    {"code": "S", "name": "Summer"},
                    {"code": "W", "name": "Winter"},
                ],
                "daynite": [
                    {"code": "D", "name": "Day"},
                    {"code": "N", "name": "Night"},
                ],
                "fractions": {
                    "SD": 0.25,
                    "SN": 0.25,
                    "WD": 0.25,
                    "WN": 0.25,
                },
            },
            "commodities": [{"name": "ELC", "type": "energy"}],
            "processes": [{"name": "P1", "sets": ["ELE"]}],
        }
    }
    jsonschema.validate(data, schema)


def test_timeslices_example_validates():
    """The example_with_timeslices.veda.yaml should pass validation."""
    schema = load_schema()
    with open(EXAMPLES_DIR / "example_with_timeslices.veda.yaml") as f:
        data = yaml.safe_load(f)
    jsonschema.validate(data, schema)


def test_timeslice_code_pattern():
    """Timeslice code must be 1-3 uppercase letters."""
    schema = load_schema()
    data = {
        "model": {
            "name": "BadTimeslice",
            "regions": ["R1"],
            "timeslices": {
                "season": [{"code": "toolong"}],
            },
            "commodities": [{"name": "ELC", "type": "energy"}],
            "processes": [{"name": "P1", "sets": ["ELE"]}],
        }
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(data, schema)


def test_trade_links_validates():
    """Trade links should validate against schema."""
    schema = load_schema()
    data = {
        "model": {
            "name": "TradeTest",
            "regions": ["REG1", "REG2"],
            "commodities": [{"name": "ELC", "type": "energy"}],
            "processes": [{"name": "P1", "sets": ["ELE"]}],
            "trade_links": [
                {
                    "origin": "REG1",
                    "destination": "REG2",
                    "commodity": "ELC",
                    "bidirectional": True,
                },
            ],
        }
    }
    jsonschema.validate(data, schema)


def test_trade_links_example_validates():
    """The example_with_trade.veda.yaml should pass validation."""
    schema = load_schema()
    with open(EXAMPLES_DIR / "example_with_trade.veda.yaml") as f:
        data = yaml.safe_load(f)
    jsonschema.validate(data, schema)


def test_trade_link_missing_required_fields():
    """Trade link missing required fields should be rejected."""
    schema = load_schema()
    data = {
        "model": {
            "name": "BadTrade",
            "regions": ["REG1", "REG2"],
            "commodities": [{"name": "ELC", "type": "energy"}],
            "processes": [{"name": "P1", "sets": ["ELE"]}],
            "trade_links": [
                {"origin": "REG1"},  # Missing destination and commodity
            ],
        }
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(data, schema)
