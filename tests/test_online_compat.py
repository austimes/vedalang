"""Tests for VEDA Online compatibility validation."""

import tempfile
from pathlib import Path

import pytest

from tools.veda_emit_excel import emit_excel
from vedalang.compiler.online_compat import validate_online_compat


def _make_tableir(tables: list[dict]) -> dict:
    """Helper to wrap tables in minimal TableIR structure."""
    return {
        "files": [
            {
                "path": "test.xlsx",
                "sheets": [{"name": "Sheet1", "tables": tables}],
            }
        ]
    }


class TestScalarTagValidation:
    def test_scalar_tag_with_extra_keys_rejected(self):
        tableir = _make_tableir([
            {"tag": "~STARTYEAR", "rows": [{"value": 2020, "extra": "bad"}]}
        ])
        errors = validate_online_compat(tableir)
        assert len(errors) == 1
        assert "extra keys" in errors[0]
        assert "extra" in errors[0]

    def test_scalar_tag_wrong_type_rejected(self):
        tableir = _make_tableir([
            {"tag": "~STARTYEAR", "rows": [{"value": "2020"}]}
        ])
        errors = validate_online_compat(tableir)
        assert len(errors) == 1
        assert "must be int" in errors[0]
        assert "str" in errors[0]

    def test_scalar_tag_valid_passes(self):
        tableir = _make_tableir([
            {"tag": "~STARTYEAR", "rows": [{"value": 2020}]}
        ])
        errors = validate_online_compat(tableir)
        assert errors == []

    def test_activepdef_scalar_valid(self):
        tableir = _make_tableir([
            {"tag": "~ACTIVEPDEF", "rows": [{"value": "P1"}]}
        ])
        errors = validate_online_compat(tableir)
        assert errors == []


class TestYearColumnValidation:
    def test_year_column_string_rejected(self):
        tableir = _make_tableir([
            {"tag": "~FI_T", "rows": [{"PRC": "P1", "year": "2020"}]}
        ])
        errors = validate_online_compat(tableir)
        assert any("'year' must be int" in e for e in errors)

    def test_year_column_null_rejected(self):
        tableir = _make_tableir([
            {"tag": "~FI_T", "rows": [{"PRC": "P1", "year": None}]}
        ])
        errors = validate_online_compat(tableir)
        assert any("null 'year'" in e for e in errors)

    def test_year_column_int_passes(self):
        tableir = _make_tableir([
            {"tag": "~FI_PROCESS", "rows": [{"PRC": "P1", "year": 2020}]}
        ])
        errors = validate_online_compat(tableir)
        assert errors == []


class TestWideAttributeColumns:
    def test_generic_value_column_rejected(self):
        tableir = _make_tableir([
            {"tag": "~FI_T", "rows": [{"PRC": "P1", "value": 100}]}
        ])
        errors = validate_online_compat(tableir)
        assert len(errors) == 1
        assert "'value' column" in errors[0]
        assert "wide-attribute" in errors[0]

    def test_value_column_in_dins_at_rejected(self):
        tableir = _make_tableir([
            {"tag": "~TFM_DINS-AT", "rows": [{"PRC": "P1", "value": 100}]}
        ])
        errors = validate_online_compat(tableir)
        assert len(errors) == 1
        assert "'value' column" in errors[0]

    def test_attribute_column_allowed_in_tfm_ins(self):
        tableir = _make_tableir([
            {"tag": "~TFM_INS", "rows": [{"attribute": "YRFR", "allregions": 0.25}]}
        ])
        errors = validate_online_compat(tableir)
        assert errors == []

    def test_named_columns_pass(self):
        tableir = _make_tableir([
            {"tag": "~FI_T", "rows": [{"PRC": "P1", "EFF": 0.55}]}
        ])
        errors = validate_online_compat(tableir)
        assert errors == []


class TestUcSetsValidation:
    def test_uc_sets_trailing_colon_rejected(self):
        tableir = _make_tableir([
            {"tag": "~UC_T", "uc_sets": {"T_E": "value:"}, "rows": []}
        ])
        errors = validate_online_compat(tableir)
        assert len(errors) == 1
        assert "trailing colon" in errors[0]

    def test_uc_sets_empty_value_passes(self):
        tableir = _make_tableir([
            {"tag": "~UC_T", "uc_sets": {"T_E": ""}, "rows": []}
        ])
        errors = validate_online_compat(tableir)
        assert errors == []

    def test_uc_sets_normal_value_passes(self):
        tableir = _make_tableir([
            {"tag": "~UC_T", "uc_sets": {"R_E": "AllRegions"}, "rows": []}
        ])
        errors = validate_online_compat(tableir)
        assert errors == []


class TestEmitExcelIntegration:
    def test_emit_excel_rejects_invalid_scalar(self):
        tableir = _make_tableir([
            {"tag": "~STARTYEAR", "rows": [{"value": 2020, "extra": "bad"}]}
        ])
        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(ValueError, match="VEDA Online compatibility"):
                emit_excel(tableir, Path(tmpdir))

    def test_emit_excel_accepts_valid_scalar(self):
        tableir = _make_tableir([
            {"tag": "~STARTYEAR", "rows": [{"value": 2020}]}
        ])
        with tempfile.TemporaryDirectory() as tmpdir:
            created = emit_excel(tableir, Path(tmpdir))
            assert len(created) == 1
