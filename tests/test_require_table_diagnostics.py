"""Tests for require_table/require_column diagnostics in xl2times.

These tests verify that missing required tables/columns emit structured
diagnostics instead of raising exceptions.
"""

import numpy as np
import pytest

from xl2times.xl2times import utils
from xl2times.xl2times.datatypes import EmbeddedXlTable, Tag
from xl2times.xl2times.diagnostics import get_collector, reset_collector, Severity
import pandas as pd


@pytest.fixture(autouse=True)
def reset_diagnostics():
    """Reset diagnostics collector before each test."""
    reset_collector()
    get_collector().enable()
    yield
    get_collector().disable()


def make_table(tag: str, data: dict) -> EmbeddedXlTable:
    """Create a minimal EmbeddedXlTable for testing."""
    return EmbeddedXlTable(
        tag=tag,
        uc_sets={},
        filename="test.xlsx",
        sheetname="Sheet1",
        range="A1:B2",
        dataframe=pd.DataFrame(data),
        defaults=None,
    )


class TestRequireTable:
    """Tests for utils.require_table()."""

    def test_returns_table_when_present(self):
        """Should return the table when it exists."""
        tables = [
            make_table("~CURRENCIES", {"currency": ["USD", "EUR"]}),
            make_table("~FI_T", {"process": ["P1"]}),
        ]

        result = utils.require_table(tables, "~CURRENCIES")
        assert result is not None
        assert result.tag == "~CURRENCIES"
        assert get_collector().get_summary()["error_count"] == 0

    def test_returns_none_and_emits_diagnostic_when_missing(self):
        """Should return None and emit diagnostic when table is missing."""
        tables = [make_table("~FI_T", {"process": ["P1"]})]

        result = utils.require_table(tables, "~CURRENCIES", feature="currency check")
        assert result is None

        summary = get_collector().get_summary()
        assert summary["error_count"] == 1

        diags = get_collector().to_dict()["diagnostics"]
        assert len(diags) == 1
        assert diags[0]["code"] == "MISSING_REQUIRED_TABLE"
        assert "~CURRENCIES" in diags[0]["message"]
        assert "currency check" in diags[0]["message"]

    def test_works_with_tag_enum(self):
        """Should work with Tag enum values."""
        tables = [make_table(Tag.currencies.value, {"currency": ["USD"]})]

        result = utils.require_table(tables, Tag.currencies)
        assert result is not None
        assert result.tag == Tag.currencies.value

    def test_no_diagnostic_when_disabled(self):
        """Should not emit diagnostic when emit_diagnostic=False."""
        tables = []

        result = utils.require_table(
            tables, "~CURRENCIES", emit_diagnostic=False
        )
        assert result is None
        assert get_collector().get_summary()["error_count"] == 0


class TestRequireColumn:
    """Tests for utils.require_column()."""

    def test_returns_column_when_present(self):
        """Should return column values when table and column exist."""
        tables = [make_table("~CURRENCIES", {"currency": ["USD", "EUR"]})]

        result = utils.require_column(tables, "~CURRENCIES", "currency")
        assert result is not None
        np.testing.assert_array_equal(result, ["USD", "EUR"])
        assert get_collector().get_summary()["error_count"] == 0

    def test_emits_diagnostic_when_table_missing(self):
        """Should emit diagnostic when table is missing."""
        tables = []

        result = utils.require_column(
            tables, "~CURRENCIES", "currency", feature="currency validation"
        )
        assert result is None

        summary = get_collector().get_summary()
        assert summary["error_count"] == 1
        diags = get_collector().to_dict()["diagnostics"]
        assert diags[0]["code"] == "MISSING_REQUIRED_TABLE"

    def test_emits_diagnostic_when_column_missing(self):
        """Should emit diagnostic when column is missing from table."""
        tables = [make_table("~CURRENCIES", {"other_col": ["X"]})]

        result = utils.require_column(
            tables, "~CURRENCIES", "currency", feature="currency validation"
        )
        assert result is None

        summary = get_collector().get_summary()
        assert summary["error_count"] == 1
        diags = get_collector().to_dict()["diagnostics"]
        assert diags[0]["code"] == "MISSING_REQUIRED_COLUMN"
        assert "currency" in diags[0]["message"]


class TestRequireScalar:
    """Tests for utils.require_scalar()."""

    def test_returns_scalar_when_present(self):
        """Should return scalar value when table is valid."""
        tables = [make_table("~STARTYEAR", {"value": [2020]})]

        result = utils.require_scalar(
            "~STARTYEAR", tables, feature="time period processing"
        )
        assert result == 2020
        assert get_collector().get_summary()["error_count"] == 0

    def test_emits_diagnostic_when_table_missing(self):
        """Should emit diagnostic when table is missing."""
        tables = []

        result = utils.require_scalar(
            "~STARTYEAR", tables, feature="time period processing"
        )
        assert result is None

        summary = get_collector().get_summary()
        assert summary["error_count"] == 1
        diags = get_collector().to_dict()["diagnostics"]
        assert diags[0]["code"] == "MISSING_REQUIRED_TABLE"

    def test_emits_diagnostic_when_not_scalar(self):
        """Should emit diagnostic when table has invalid shape."""
        tables = [make_table("~STARTYEAR", {"value": [2020, 2025]})]

        result = utils.require_scalar(
            "~STARTYEAR", tables, feature="time period processing"
        )
        assert result is None

        summary = get_collector().get_summary()
        assert summary["error_count"] == 1
        diags = get_collector().to_dict()["diagnostics"]
        assert diags[0]["code"] == "INVALID_SCALAR_TABLE"
        assert "one value" in diags[0]["message"]


class TestDiagnosticCodes:
    """Tests to verify diagnostic codes are consistent."""

    def test_missing_table_code(self):
        """MISSING_REQUIRED_TABLE code should be used for missing tables."""
        tables = []
        utils.require_table(tables, "~NONEXISTENT")

        diags = get_collector().to_dict()["diagnostics"]
        assert diags[0]["code"] == "MISSING_REQUIRED_TABLE"
        assert diags[0]["severity"] == "error"

    def test_missing_column_code(self):
        """MISSING_REQUIRED_COLUMN code should be used for missing columns."""
        tables = [make_table("~TEST", {"other": [1]})]
        utils.require_column(tables, "~TEST", "missing_col")

        diags = get_collector().to_dict()["diagnostics"]
        assert diags[0]["code"] == "MISSING_REQUIRED_COLUMN"

    def test_invalid_scalar_code(self):
        """INVALID_SCALAR_TABLE code should be used for invalid scalar tables."""
        tables = [make_table("~TEST", {"value": [1, 2, 3]})]
        utils.require_scalar("~TEST", tables)

        diags = get_collector().to_dict()["diagnostics"]
        assert diags[0]["code"] == "INVALID_SCALAR_TABLE"
