"""Tests for TableIR JSON Schema validation."""

import json
from pathlib import Path

import jsonschema
import pytest


@pytest.fixture
def tableir_schema():
    """Load the TableIR schema."""
    schema_path = Path(__file__).parent.parent / "vedalang" / "schema" / "tableir.schema.json"
    with open(schema_path) as f:
        return json.load(f)


@pytest.fixture
def valid_tableir():
    """Minimal valid TableIR example from AGENTS.md."""
    return {
        "files": [
            {
                "path": "base/base.xlsx",
                "sheets": [
                    {
                        "name": "Base",
                        "tables": [
                            {
                                "tag": "~FI_PROCESS",
                                "rows": [
                                    {"PRC": "PP_CCGT", "Sets": "ELE", "TACT": "PJ", "TCAP": "GW"}
                                ]
                            },
                            {
                                "tag": "~FI_T",
                                "rows": [
                                    {"PRC": "PP_CCGT", "COM_IN": "NG", "COM_OUT": "ELC", "EFF": 0.55}
                                ]
                            }
                        ]
                    }
                ]
            }
        ]
    }


def test_schema_loads(tableir_schema):
    """Schema file exists and is valid JSON."""
    assert tableir_schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert tableir_schema["title"] == "TableIR"


def test_valid_tableir_passes(tableir_schema, valid_tableir):
    """Valid TableIR data passes validation."""
    jsonschema.validate(valid_tableir, tableir_schema)


def test_empty_files_array_valid(tableir_schema):
    """Empty files array is valid."""
    jsonschema.validate({"files": []}, tableir_schema)


def test_missing_files_rejected(tableir_schema):
    """Missing required 'files' property is rejected."""
    with pytest.raises(jsonschema.ValidationError) as exc_info:
        jsonschema.validate({}, tableir_schema)
    assert "'files' is a required property" in str(exc_info.value)


def test_missing_path_rejected(tableir_schema):
    """Missing required 'path' in file is rejected."""
    invalid = {"files": [{"sheets": []}]}
    with pytest.raises(jsonschema.ValidationError) as exc_info:
        jsonschema.validate(invalid, tableir_schema)
    assert "'path' is a required property" in str(exc_info.value)


def test_missing_sheets_rejected(tableir_schema):
    """Missing required 'sheets' in file is rejected."""
    invalid = {"files": [{"path": "base.xlsx"}]}
    with pytest.raises(jsonschema.ValidationError) as exc_info:
        jsonschema.validate(invalid, tableir_schema)
    assert "'sheets' is a required property" in str(exc_info.value)


def test_tag_must_start_with_tilde(tableir_schema):
    """Tag must start with ~ character."""
    invalid = {
        "files": [{
            "path": "test.xlsx",
            "sheets": [{
                "name": "Sheet1",
                "tables": [{
                    "tag": "FI_PROCESS",  # Missing ~
                    "rows": []
                }]
            }]
        }]
    }
    with pytest.raises(jsonschema.ValidationError) as exc_info:
        jsonschema.validate(invalid, tableir_schema)
    assert "does not match" in str(exc_info.value) or "pattern" in str(exc_info.value).lower()


def test_row_values_string_number_boolean(tableir_schema):
    """Row values can be string, number, or boolean."""
    valid = {
        "files": [{
            "path": "test.xlsx",
            "sheets": [{
                "name": "Sheet1",
                "tables": [{
                    "tag": "~FI_T",
                    "rows": [{
                        "string_col": "value",
                        "number_col": 42,
                        "float_col": 3.14,
                        "bool_col": True
                    }]
                }]
            }]
        }]
    }
    jsonschema.validate(valid, tableir_schema)


def test_row_nested_object_rejected(tableir_schema):
    """Nested objects in rows are rejected."""
    invalid = {
        "files": [{
            "path": "test.xlsx",
            "sheets": [{
                "name": "Sheet1",
                "tables": [{
                    "tag": "~FI_T",
                    "rows": [{
                        "nested": {"invalid": "object"}
                    }]
                }]
            }]
        }]
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(invalid, tableir_schema)
