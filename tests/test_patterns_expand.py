"""Tests for pattern expansion."""

import json
from pathlib import Path

import pytest
import yaml

from tools.veda_patterns import (
    PatternError,
    expand_pattern,
    get_pattern_info,
    list_patterns,
)

PROJECT_ROOT = Path(__file__).parent.parent
SCHEMA_DIR = PROJECT_ROOT / "vedalang" / "schema"


class TestListPatterns:
    def test_list_returns_patterns(self):
        """Should return list of available patterns."""
        patterns = list_patterns()
        assert isinstance(patterns, list)
        assert len(patterns) > 0
        assert "add_power_plant" in patterns

    def test_get_pattern_info(self):
        """Should return pattern details."""
        info = get_pattern_info("add_power_plant")
        assert "description" in info
        assert "parameters" in info


class TestExpandPattern:
    def test_expand_power_plant(self):
        """Expand add_power_plant pattern."""
        result = expand_pattern(
            "add_power_plant",
            {
                "plant_name": "PP_TEST",
                "fuel_commodity": "COAL",
                "output_commodity": "ELC",
            },
            output_format="vedalang"
        )

        # Should be valid YAML
        parsed = yaml.safe_load(result)
        assert "processes" in parsed
        assert parsed["processes"][0]["name"] == "PP_TEST"

    def test_expand_with_defaults(self):
        """Default values should be applied."""
        result = expand_pattern(
            "add_power_plant",
            {
                "plant_name": "PP_DEFAULT",
                "fuel_commodity": "NG",
                "output_commodity": "ELC",
                # efficiency not specified, should use default
            },
            output_format="vedalang"
        )

        parsed = yaml.safe_load(result)
        # Should have efficiency from default (0.40)
        assert parsed["processes"][0]["efficiency"] == 0.40

    def test_missing_required_param_raises(self):
        """Missing required parameter should raise PatternError."""
        with pytest.raises(PatternError, match="Missing required parameter"):
            expand_pattern(
                "add_power_plant",
                {"fuel_commodity": "NG"},  # Missing plant_name
                output_format="vedalang"
            )

    def test_unknown_pattern_raises(self):
        """Unknown pattern should raise PatternError."""
        with pytest.raises(PatternError, match="Unknown pattern"):
            expand_pattern("nonexistent_pattern", {})


class TestFullPipeline:
    def test_expand_compile_validate(self):
        """Expand pattern, wrap in model, compile to TableIR, validate."""
        import jsonschema

        from vedalang.compiler import compile_vedalang_to_tableir

        # Expand pattern
        process_yaml = expand_pattern(
            "add_power_plant",
            {
                "plant_name": "PP_CCGT",
                "fuel_commodity": "NG",
                "output_commodity": "ELC",
                "efficiency": 0.55,
            }
        )
        process_data = yaml.safe_load(process_yaml)

        # Also expand commodities
        elc_yaml = expand_pattern(
            "add_energy_commodity",
            {"name": "ELC", "unit": "PJ"}
        )
        ng_yaml = expand_pattern(
            "add_energy_commodity",
            {"name": "NG", "unit": "PJ"}
        )

        elc_data = yaml.safe_load(elc_yaml)
        ng_data = yaml.safe_load(ng_yaml)

        # Build full VedaLang model
        model = {
            "model": {
                "name": "PatternTest",
                "regions": ["REG1"],
                "commodities": elc_data["commodities"] + ng_data["commodities"],
                "processes": process_data["processes"],
            }
        }

        # Compile to TableIR
        tableir = compile_vedalang_to_tableir(model)

        # Validate against schema
        with open(SCHEMA_DIR / "tableir.schema.json") as f:
            schema = json.load(f)

        jsonschema.validate(tableir, schema)
