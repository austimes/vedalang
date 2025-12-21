"""Tests for TableIR invariant checking."""

from tools.veda_check.invariants import check_tableir_invariants


def make_tableir(tables: list[dict]) -> dict:
    """Helper to create TableIR structure with given tables."""
    return {
        "files": [
            {
                "path": "test/test.xlsx",
                "sheets": [{"name": "Test", "tables": tables}],
            }
        ]
    }


class TestFiCommConstraints:
    """Tests for ~FI_COMM required fields: Csets, CommName."""

    def test_valid_fi_comm_passes(self):
        tableir = make_tableir([
            {
                "tag": "~FI_COMM",
                "rows": [{"csets": "NRG", "commname": "ELC"}],
            }
        ])
        errors = check_tableir_invariants(tableir)
        assert errors == []

    def test_missing_csets(self):
        tableir = make_tableir([
            {
                "tag": "~FI_COMM",
                "rows": [{"commname": "ELC"}],
            }
        ])
        errors = check_tableir_invariants(tableir)
        assert len(errors) == 1
        assert "Csets" in errors[0]
        assert "missing required field" in errors[0]

    def test_missing_commname(self):
        tableir = make_tableir([
            {
                "tag": "~FI_COMM",
                "rows": [{"csets": "NRG"}],
            }
        ])
        errors = check_tableir_invariants(tableir)
        assert len(errors) == 1
        assert "CommName" in errors[0]

    def test_multiple_missing_fields(self):
        tableir = make_tableir([
            {
                "tag": "~FI_COMM",
                "rows": [{"unit": "PJ"}],
            }
        ])
        errors = check_tableir_invariants(tableir)
        assert len(errors) == 2


class TestFiProcessConstraints:
    """Tests for ~FI_PROCESS required fields: TechName, Sets."""

    def test_valid_fi_process_passes(self):
        tableir = make_tableir([
            {
                "tag": "~FI_PROCESS",
                "rows": [{"techname": "PP_CCGT", "sets": "ELE"}],
            }
        ])
        errors = check_tableir_invariants(tableir)
        assert errors == []

    def test_missing_techname(self):
        tableir = make_tableir([
            {
                "tag": "~FI_PROCESS",
                "rows": [{"sets": "ELE"}],
            }
        ])
        errors = check_tableir_invariants(tableir)
        assert len(errors) == 1
        assert "TechName" in errors[0]

    def test_missing_sets(self):
        tableir = make_tableir([
            {
                "tag": "~FI_PROCESS",
                "rows": [{"techname": "PP_CCGT"}],
            }
        ])
        errors = check_tableir_invariants(tableir)
        assert len(errors) == 1
        assert "Sets" in errors[0]


class TestFiTConstraints:
    """Tests for ~FI_T required fields: TechName, and (Comm-IN or Comm-OUT or EFF)."""

    def test_valid_fi_t_with_comm_in(self):
        tableir = make_tableir([
            {
                "tag": "~FI_T",
                "rows": [{"techname": "PP_CCGT", "commodity-in": "NG"}],
            }
        ])
        errors = check_tableir_invariants(tableir)
        assert errors == []

    def test_valid_fi_t_with_comm_out(self):
        tableir = make_tableir([
            {
                "tag": "~FI_T",
                "rows": [{"techname": "PP_CCGT", "commodity-out": "ELC"}],
            }
        ])
        errors = check_tableir_invariants(tableir)
        assert errors == []

    def test_valid_fi_t_with_both_comm(self):
        tableir = make_tableir([
            {
                "tag": "~FI_T",
                "rows": [
                    {
                        "techname": "PP_CCGT",
                        "commodity-in": "NG",
                        "commodity-out": "ELC",
                    }
                ],
            }
        ])
        errors = check_tableir_invariants(tableir)
        assert errors == []

    def test_valid_fi_t_with_eff_only(self):
        tableir = make_tableir([
            {
                "tag": "~FI_T",
                "rows": [{"techname": "PP_CCGT", "eff": 0.55}],
            }
        ])
        errors = check_tableir_invariants(tableir)
        assert errors == []

    def test_missing_techname(self):
        tableir = make_tableir([
            {
                "tag": "~FI_T",
                "rows": [{"commodity-in": "NG"}],
            }
        ])
        errors = check_tableir_invariants(tableir)
        assert len(errors) == 1
        assert "TechName" in errors[0]

    def test_missing_all_data_fields(self):
        tableir = make_tableir([
            {
                "tag": "~FI_T",
                "rows": [{"techname": "PP_CCGT", "region": "REG1"}],
            }
        ])
        errors = check_tableir_invariants(tableir)
        assert len(errors) == 1
        assert "Comm-IN" in errors[0]
        assert "Comm-OUT" in errors[0]
        assert "EFF" in errors[0]


class TestMultipleRowsAndTables:
    """Tests for validation across multiple rows and tables."""

    def test_multiple_rows_all_valid(self):
        tableir = make_tableir([
            {
                "tag": "~FI_COMM",
                "rows": [
                    {"csets": "NRG", "commname": "ELC"},
                    {"csets": "NRG", "commname": "NG"},
                    {"csets": "ENV", "commname": "CO2"},
                ],
            }
        ])
        errors = check_tableir_invariants(tableir)
        assert errors == []

    def test_multiple_rows_some_invalid(self):
        tableir = make_tableir([
            {
                "tag": "~FI_COMM",
                "rows": [
                    {"csets": "NRG", "commname": "ELC"},
                    {"csets": "NRG"},
                    {"commname": "CO2"},
                ],
            }
        ])
        errors = check_tableir_invariants(tableir)
        assert len(errors) == 2
        assert "row 2" in errors[0]
        assert "row 3" in errors[1]

    def test_multiple_tables(self):
        tableir = make_tableir([
            {
                "tag": "~FI_COMM",
                "rows": [{"csets": "NRG", "commname": "ELC"}],
            },
            {
                "tag": "~FI_PROCESS",
                "rows": [{"techname": "PP_CCGT", "sets": "ELE"}],
            },
        ])
        errors = check_tableir_invariants(tableir)
        assert errors == []


class TestCanonicalFormEnforcement:
    """Tests that canonical form rules are enforced."""

    def test_lowercase_fields_pass(self):
        """Lowercase column names are the canonical form."""
        tableir = make_tableir([
            {
                "tag": "~FI_COMM",
                "rows": [{"csets": "NRG", "commname": "ELC"}],
            }
        ])
        errors = check_tableir_invariants(tableir)
        assert errors == []

    def test_uppercase_fields_rejected(self):
        """Uppercase column names violate canonical form."""
        tableir = make_tableir([
            {
                "tag": "~FI_COMM",
                "rows": [{"Csets": "NRG", "CommName": "ELC"}],
            }
        ])
        errors = check_tableir_invariants(tableir)
        assert len(errors) >= 1
        assert any("lowercase" in e for e in errors)

    def test_year_columns_rejected(self):
        """Year values as column names are forbidden (wide pivot)."""
        tableir = make_tableir([
            {
                "tag": "~TFM_INS-TS",
                "rows": [{"region": "REG1", "2020": 100, "2030": 200}],
            }
        ])
        errors = check_tableir_invariants(tableir)
        assert len(errors) >= 1
        assert any("year" in e.lower() for e in errors)

    def test_dense_time_series_valid(self):
        """Dense time-series data (one row per year) is the canonical form."""
        tableir = make_tableir([
            {
                "tag": "~TFM_INS-TS",
                "rows": [
                    {"region": "REG1", "year": 2020, "pset_co": "CO2", "cost": 50},
                    {"region": "REG1", "year": 2030, "pset_co": "CO2", "cost": 100},
                    {"region": "REG1", "year": 2040, "pset_co": "CO2", "cost": 150},
                ],
            }
        ])
        errors = check_tableir_invariants(tableir)
        # Dense data should pass validation
        assert errors == []


class TestUnknownTags:
    """Tests that unknown tags are ignored (not an error)."""

    def test_unknown_tag_ignored(self):
        tableir = make_tableir([
            {
                "tag": "~CUSTOM_TAG",
                "rows": [{"anything": "value"}],
            }
        ])
        errors = check_tableir_invariants(tableir)
        assert errors == []
