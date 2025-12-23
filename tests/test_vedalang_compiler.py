"""Tests for VedaLang compiler."""

import json
from pathlib import Path

import jsonschema
import pytest

from vedalang.compiler import (
    SemanticValidationError,
    compile_vedalang_to_tableir,
    load_vedalang,
    validate_cross_references,
)

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
    comm_names = [r.get("commodity") for r in comm_tables[0]["rows"]]
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
    tech_names = [r.get("process") for r in proc_tables[0]["rows"]]
    assert "PP_CCGT" in tech_names


def test_invalid_vedalang_rejected():
    """Invalid VedaLang should raise ValidationError."""
    invalid = {"not_a_model": True}
    with pytest.raises(jsonschema.ValidationError):
        compile_vedalang_to_tableir(invalid)


def test_process_cost_attributes():
    """Process cost attributes should appear in ~FI_T table."""
    source = {
        "model": {
            "name": "CostTest",
            "regions": ["REG1"],
            "commodities": [
                {"name": "NG", "type": "energy"},
                {"name": "ELC", "type": "energy"},
            ],
            "processes": [
                {
                    "name": "PP_CCGT",
                    "sets": ["ELE"],
                    "primary_commodity_group": "NRGO",
                    "inputs": [{"commodity": "NG"}],
                    "outputs": [{"commodity": "ELC"}],
                    "efficiency": 0.55,
                    "invcost": 800,
                    "fixom": 20,
                    "varom": 2,
                    "life": 30,
                },
                {
                    "name": "IMP_NG",
                    "sets": ["IMP"],
                    "primary_commodity_group": "NRGO",
                    "outputs": [{"commodity": "NG"}],
                    "cost": 5.0,
                },
            ],
        }
    }
    tableir = compile_vedalang_to_tableir(source)

    # Find ~FI_T table
    fit_rows = []
    for f in tableir["files"]:
        for s in f["sheets"]:
            for t in s["tables"]:
                if t["tag"] == "~FI_T":
                    fit_rows.extend(t["rows"])

    # Find the cost row for PP_CCGT (has eff, ncap_cost, ncap_fom, act_cost, ncap_tlife)
    # Note: VedaLang emits CANONICAL column names, not aliases
    ccgt_cost_rows = [
        r for r in fit_rows if r.get("process") == "PP_CCGT" and "eff" in r
    ]
    assert len(ccgt_cost_rows) == 1
    ccgt_row = ccgt_cost_rows[0]
    assert ccgt_row["eff"] == 0.55
    assert ccgt_row["ncap_cost"] == 800  # canonical for invcost
    assert ccgt_row["ncap_fom"] == 20  # canonical for fixom
    assert ccgt_row["act_cost"] == 2  # canonical for varom
    assert ccgt_row["ncap_tlife"] == 30  # canonical for life

    # Find the cost row for IMP_NG (ire_price merged into commodity-out row)
    imp_cost_rows = [
        r for r in fit_rows if r.get("process") == "IMP_NG" and "ire_price" in r
    ]
    assert len(imp_cost_rows) == 1
    assert imp_cost_rows[0]["ire_price"] == 5.0  # canonical for cost
    assert imp_cost_rows[0]["commodity-out"] == "NG"  # Merged into output row


def test_demand_projection_scenario():
    """demand_projection scenario should emit to ~FI_T with attribute=DEMAND."""
    source = {
        "model": {
            "name": "DemandTest",
            "regions": ["REG1"],
            "start_year": 2020,
            "time_periods": [10, 10, 10, 10],
            "commodities": [
                {"name": "ELC", "type": "energy"},
                {"name": "RSD", "type": "demand"},
            ],
            "processes": [
                {
                    "name": "DEM_RSD",
                    "sets": ["DMD"],
                    "primary_commodity_group": "DEMO",
                    "inputs": [{"commodity": "ELC"}],
                    "outputs": [{"commodity": "RSD"}],
                    "efficiency": 1.0,
                },
            ],
            "scenarios": [
                {
                    "name": "BaseDemand",
                    "type": "demand_projection",
                    "commodity": "RSD",
                    "interpolation": "interp_extrap",
                    "values": {
                        "2020": 100.0,
                        "2030": 120.0,
                        "2050": 160.0,
                    },
                },
            ],
        }
    }
    tableir = compile_vedalang_to_tableir(source)

    # Find ~FI_T table
    fit_rows = []
    for f in tableir["files"]:
        for s in f["sheets"]:
            for t in s["tables"]:
                if t["tag"] == "~FI_T":
                    fit_rows.extend(t["rows"])

    # Find demand projection rows (wide-in-attribute format)
    # NOTE: Use canonical 'com_proj', not alias 'demand'
    demand_rows = [r for r in fit_rows if "com_proj" in r]

    # Should have 4 rows (one per model year: 2020, 2030, 2040, 2050)
    assert len(demand_rows) == 4

    # Check years are present
    years = sorted([r["year"] for r in demand_rows])
    assert years == [2020, 2030, 2040, 2050]

    # Check commodity is correct
    for row in demand_rows:
        assert row["commodity"] == "RSD"
        assert row["region"] == "REG1"

    # Check values are interpolated correctly (com_proj is column header, not 'value')
    values_by_year = {r["year"]: r["com_proj"] for r in demand_rows}
    assert values_by_year[2020] == 100.0
    assert values_by_year[2030] == 120.0
    assert values_by_year[2040] == 140.0  # Interpolated between 120 and 160
    assert values_by_year[2050] == 160.0


def test_demand_projection_no_scenario_file():
    """demand_projection should NOT create a separate scenario file."""
    source = {
        "model": {
            "name": "DemandTest",
            "regions": ["REG1"],
            "commodities": [
                {"name": "RSD", "type": "demand"},
            ],
            "processes": [
                {
                    "name": "DEM_RSD",
                    "sets": ["DMD"],
                    "primary_commodity_group": "DEMO",
                    "outputs": [{"commodity": "RSD"}],
                },
            ],
            "scenarios": [
                {
                    "name": "BaseDemand",
                    "type": "demand_projection",
                    "commodity": "RSD",
                    "interpolation": "interp_extrap",
                    "values": {"2020": 100.0},
                },
            ],
        }
    }
    tableir = compile_vedalang_to_tableir(source)

    # Should NOT have a Scen_BaseDemand file
    file_paths = [f["path"] for f in tableir["files"]]
    assert not any("Scen_BaseDemand" in p for p in file_paths)


def test_process_capacity_bounds():
    """Process bounds should emit rows with limtype column."""
    source = {
        "model": {
            "name": "BoundsTest",
            "regions": ["REG1"],
            "commodities": [
                {"name": "ELC", "type": "energy"},
            ],
            "processes": [
                {
                    "name": "PP_CCGT",
                    "sets": ["ELE"],
                    "primary_commodity_group": "NRGO",
                    "outputs": [{"commodity": "ELC"}],
                    "cap_bound": {"up": 10.0},
                    "ncap_bound": {"up": 2.0, "lo": 0.5},
                },
            ],
        }
    }
    tableir = compile_vedalang_to_tableir(source)

    # Find ~FI_T rows
    fit_rows = []
    for f in tableir["files"]:
        for s in f["sheets"]:
            for t in s["tables"]:
                if t["tag"] == "~FI_T":
                    fit_rows.extend(t["rows"])

    # Find bound rows
    bound_rows = [r for r in fit_rows if "limtype" in r]
    assert len(bound_rows) == 3  # cap_bnd UP, ncap_bnd UP, ncap_bnd LO

    # Check cap_bnd upper bound
    cap_up = [r for r in bound_rows if r.get("cap_bnd") == 10.0]
    assert len(cap_up) == 1
    assert cap_up[0]["limtype"] == "UP"
    assert cap_up[0]["process"] == "PP_CCGT"

    # Check ncap_bnd upper bound
    ncap_up = [r for r in bound_rows if r.get("ncap_bnd") == 2.0]
    assert len(ncap_up) == 1
    assert ncap_up[0]["limtype"] == "UP"

    # Check ncap_bnd lower bound
    ncap_lo = [r for r in bound_rows if r.get("ncap_bnd") == 0.5]
    assert len(ncap_lo) == 1
    assert ncap_lo[0]["limtype"] == "LO"


def test_process_activity_bound():
    """Activity bounds should emit rows with act_bnd column."""
    source = {
        "model": {
            "name": "ActBoundTest",
            "regions": ["REG1"],
            "commodities": [
                {"name": "NG", "type": "energy"},
            ],
            "processes": [
                {
                    "name": "IMP_NG",
                    "sets": ["IMP"],
                    "primary_commodity_group": "NRGO",
                    "outputs": [{"commodity": "NG"}],
                    "activity_bound": {"up": 500.0, "fx": 100.0},
                },
            ],
        }
    }
    tableir = compile_vedalang_to_tableir(source)

    # Find ~FI_T rows
    fit_rows = []
    for f in tableir["files"]:
        for s in f["sheets"]:
            for t in s["tables"]:
                if t["tag"] == "~FI_T":
                    fit_rows.extend(t["rows"])

    # Find activity bound rows
    act_rows = [r for r in fit_rows if "act_bnd" in r]
    assert len(act_rows) == 2

    # Check UP bound
    act_up = [r for r in act_rows if r["limtype"] == "UP"]
    assert len(act_up) == 1
    assert act_up[0]["act_bnd"] == 500.0

    # Check FX bound
    act_fx = [r for r in act_rows if r["limtype"] == "FX"]
    assert len(act_fx) == 1
    assert act_fx[0]["act_bnd"] == 100.0


def test_compile_example_with_bounds():
    """Compile example_with_bounds.veda.yaml to TableIR."""
    source = load_vedalang(EXAMPLES_DIR / "example_with_bounds.veda.yaml")
    tableir = compile_vedalang_to_tableir(source)

    # Find ~FI_T rows
    fit_rows = []
    for f in tableir["files"]:
        for s in f["sheets"]:
            for t in s["tables"]:
                if t["tag"] == "~FI_T":
                    fit_rows.extend(t["rows"])

    # Check that bounds are present
    bound_rows = [r for r in fit_rows if "limtype" in r]
    assert len(bound_rows) >= 6  # Multiple bounds across processes

    # Verify specific bounds exist
    ccgt_cap_up = [
        r
        for r in bound_rows
        if r.get("process") == "PP_CCGT" and r.get("cap_bnd") == 10.0
    ]
    assert len(ccgt_cap_up) == 1

    wind_cap_lo = [
        r
        for r in bound_rows
        if r.get("process") == "PP_WIND" and r.get("limtype") == "LO"
    ]
    assert len(wind_cap_lo) == 1
    assert wind_cap_lo[0]["cap_bnd"] == 5.0


def test_compile_timeslices():
    """Timeslices should emit ~TIMESLICES and ~TFM_INS (YRFR) tables."""
    source = {
        "model": {
            "name": "TimesliceTest",
            "regions": ["REG1"],
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
                    "SN": 0.23,
                    "WD": 0.27,
                    "WN": 0.25,
                },
            },
            "commodities": [
                {"name": "ELC", "type": "energy"},
            ],
            "processes": [
                {
                    "name": "PP_CCGT",
                    "sets": ["ELE"],
                    "primary_commodity_group": "NRGO",
                    "outputs": [{"commodity": "ELC"}],
                },
            ],
        }
    }
    tableir = compile_vedalang_to_tableir(source)

    # Find ~TIMESLICES table
    timeslice_tables = []
    for f in tableir["files"]:
        for s in f["sheets"]:
            for t in s["tables"]:
                if t["tag"] == "~TIMESLICES":
                    timeslice_tables.append(t)

    assert len(timeslice_tables) == 1
    ts_rows = timeslice_tables[0]["rows"]

    # Should have 4 rows (2 seasons × 2 daynite)
    assert len(ts_rows) == 4

    # Check structure
    seasons = {r["season"] for r in ts_rows}
    daynites = {r["daynite"] for r in ts_rows}
    assert seasons == {"S", "W"}
    assert daynites == {"D", "N"}

    # Each row should have weekly column (empty)
    for row in ts_rows:
        assert "weekly" in row
        assert row["weekly"] == ""


def test_compile_timeslices_yrfr():
    """Timeslice fractions should emit ~TFM_INS rows with attribute=YRFR."""
    source = {
        "model": {
            "name": "TimesliceYRFRTest",
            "regions": ["REG1"],
            "timeslices": {
                "season": [{"code": "S"}, {"code": "W"}],
                "daynite": [{"code": "D"}, {"code": "N"}],
                "fractions": {
                    "SD": 0.25,
                    "SN": 0.23,
                    "WD": 0.27,
                    "WN": 0.25,
                },
            },
            "commodities": [{"name": "ELC", "type": "energy"}],
            "processes": [
                {"name": "PP_CCGT", "sets": ["ELE"], "primary_commodity_group": "NRGO"}
            ],
        }
    }
    tableir = compile_vedalang_to_tableir(source)

    # Find ~TFM_INS table in SysSettings
    tfm_ins_rows = []
    for f in tableir["files"]:
        if "SysSettings" in f["path"]:
            for s in f["sheets"]:
                for t in s["tables"]:
                    if t["tag"] == "~TFM_INS":
                        tfm_ins_rows.extend(t["rows"])

    # Should have 4 YRFR rows
    yrfr_rows = [r for r in tfm_ins_rows if r.get("attribute") == "YRFR"]
    assert len(yrfr_rows) == 4

    # Check values
    by_ts = {r["timeslice"]: r["allregions"] for r in yrfr_rows}
    assert by_ts["SD"] == 0.25
    assert by_ts["SN"] == 0.23
    assert by_ts["WD"] == 0.27
    assert by_ts["WN"] == 0.25


def test_compile_example_with_timeslices():
    """Compile example_with_timeslices.veda.yaml to TableIR."""
    source = load_vedalang(EXAMPLES_DIR / "example_with_timeslices.veda.yaml")
    tableir = compile_vedalang_to_tableir(source)

    # Should have timeslice table
    has_timeslices = False
    for f in tableir["files"]:
        for s in f["sheets"]:
            for t in s["tables"]:
                if t["tag"] == "~TIMESLICES":
                    has_timeslices = True
                    assert len(t["rows"]) == 4

    assert has_timeslices


def test_no_timeslices_when_not_defined():
    """Models without timeslices should not emit ~TIMESLICES table."""
    source = load_vedalang(EXAMPLES_DIR / "mini_plant.veda.yaml")
    tableir = compile_vedalang_to_tableir(source)

    # Should NOT have timeslice table
    for f in tableir["files"]:
        for s in f["sheets"]:
            for t in s["tables"]:
                assert t["tag"] != "~TIMESLICES"


def test_compile_trade_links():
    """Trade links should emit ~TRADELINKS tables (matrix format)."""
    source = {
        "model": {
            "name": "TradeTest",
            "regions": ["REG1", "REG2"],
            "commodities": [
                {"name": "ELC", "type": "energy"},
                {"name": "NG", "type": "energy"},
            ],
            "processes": [
                {
                    "name": "PP_CCGT",
                    "sets": ["ELE"],
                    "primary_commodity_group": "NRGO",
                    "outputs": [{"commodity": "ELC"}],
                },
            ],
            "trade_links": [
                {
                    "origin": "REG1",
                    "destination": "REG2",
                    "commodity": "ELC",
                    "bidirectional": True,
                },
                {
                    "origin": "REG1",
                    "destination": "REG2",
                    "commodity": "NG",
                    "bidirectional": False,
                },
            ],
        }
    }
    tableir = compile_vedalang_to_tableir(source)

    # Find ~TRADELINKS tables and sheet names
    tradelinks_tables = []
    sheet_names = []
    for f in tableir["files"]:
        for s in f["sheets"]:
            for t in s["tables"]:
                if t["tag"] == "~TRADELINKS":
                    tradelinks_tables.append(t)
                    sheet_names.append(s["name"])

    # Should have 2 sheets: Bi_ELC and Uni_NG
    assert len(tradelinks_tables) == 2
    assert "Bi_ELC" in sheet_names
    assert "Uni_NG" in sheet_names

    # Check bidirectional ELC link (matrix format with process name as value)
    bi_elc_idx = sheet_names.index("Bi_ELC")
    elc_rows = tradelinks_tables[bi_elc_idx]["rows"]
    assert len(elc_rows) == 1  # One origin (REG1)
    assert elc_rows[0]["ELC"] == "REG1"  # First column is commodity, value is origin
    assert elc_rows[0]["REG2"] == "T_B_ELC_REG1_REG2_01"  # Explicit process name

    # Check unidirectional NG link
    uni_ng_idx = sheet_names.index("Uni_NG")
    ng_rows = tradelinks_tables[uni_ng_idx]["rows"]
    assert len(ng_rows) == 1
    assert ng_rows[0]["NG"] == "REG1"
    assert ng_rows[0]["REG2"] == "T_U_NG_REG1_REG2_01"


def test_trade_links_file_path():
    """Trade links should be in SuppXLS/Trades directory."""
    source = {
        "model": {
            "name": "TestModel",
            "regions": ["REG1", "REG2"],
            "commodities": [{"name": "ELC", "type": "energy"}],
            "processes": [
                {"name": "PP", "sets": ["ELE"], "primary_commodity_group": "NRGO"}
            ],
            "trade_links": [
                {"origin": "REG1", "destination": "REG2", "commodity": "ELC"},
            ],
        }
    }
    tableir = compile_vedalang_to_tableir(source)

    # Find trade file path (in SuppXLS/Trades)
    trade_files = [
        f["path"] for f in tableir["files"] if f["path"].startswith("SuppXLS/Trades/")
    ]
    assert len(trade_files) == 1
    assert trade_files[0] == "SuppXLS/Trades/ScenTrade__Trade_Links.xlsx"


def test_no_trade_links_when_not_defined():
    """Models without trade_links should not emit trade file."""
    source = load_vedalang(EXAMPLES_DIR / "mini_plant.veda.yaml")
    tableir = compile_vedalang_to_tableir(source)

    # Should NOT have trade file
    for f in tableir["files"]:
        assert "Trade" not in f["path"]
        for s in f["sheets"]:
            for t in s["tables"]:
                assert t["tag"] != "~TRADELINKS"


def test_compile_example_with_trade():
    """Compile example_with_trade.veda.yaml to TableIR."""
    source = load_vedalang(EXAMPLES_DIR / "example_with_trade.veda.yaml")
    tableir = compile_vedalang_to_tableir(source)

    # Should have trade links file in SuppXLS/Trades
    trade_files = [
        f for f in tableir["files"] if f["path"].startswith("SuppXLS/Trades/")
    ]
    assert len(trade_files) == 1

    # Should have ~TRADELINKS tables (2 sheets for 2 commodities, both bidirectional)
    tradelinks_tables = []
    for s in trade_files[0]["sheets"]:
        for t in s["tables"]:
            if t["tag"] == "~TRADELINKS":
                tradelinks_tables.append(t)
    assert len(tradelinks_tables) == 2

    # VedaOnline compatibility: ~FI_T tables go to base VT_* file, NOT ScenTrade
    # Trade efficiency rows should be in the main process file's ~FI_T table
    base_file = [f for f in tableir["files"] if f["path"].startswith("VT_")][0]
    fit_rows = []
    for s in base_file["sheets"]:
        for t in s["tables"]:
            if t["tag"] == "~FI_T":
                fit_rows.extend(t["rows"])
    # Check trade efficiency row is present (ELC has efficiency 0.98)
    trade_eff_rows = [r for r in fit_rows if r.get("process", "").startswith("T_")]
    assert any(r.get("eff") == 0.98 for r in trade_eff_rows)


def test_trade_link_efficiency():
    """Trade links with efficiency should emit ~FI_T row in base VT_* file.

    VedaOnline compatibility: ~FI_T tables are NOT allowed in ScenTrade files,
    so trade efficiency rows go to the base VT_* file.
    """
    source = {
        "model": {
            "name": "TradeEffTest",
            "regions": ["REG1", "REG2"],
            "commodities": [{"name": "ELC", "type": "energy"}],
            "processes": [
                {"name": "PP", "sets": ["ELE"], "primary_commodity_group": "NRGO"}
            ],
            "trade_links": [
                {
                    "origin": "REG1",
                    "destination": "REG2",
                    "commodity": "ELC",
                    "bidirectional": True,
                    "efficiency": 0.95,  # 5% transmission loss
                },
            ],
        }
    }
    tableir = compile_vedalang_to_tableir(source)

    # Find trade file
    trade_files = [
        f for f in tableir["files"] if f["path"].startswith("SuppXLS/Trades/")
    ]
    assert len(trade_files) == 1

    # Should have ~TRADELINKS table with process name
    tradelinks_tables = []
    for s in trade_files[0]["sheets"]:
        for t in s["tables"]:
            if t["tag"] == "~TRADELINKS":
                tradelinks_tables.append(t)
    assert len(tradelinks_tables) == 1
    # Check that we emit process name (not just 1) to enable efficiency targeting
    assert tradelinks_tables[0]["rows"][0]["REG2"] == "T_B_ELC_REG1_REG2_01"

    # VedaOnline: ~FI_T goes to base VT_* file, NOT trade file
    base_file = [f for f in tableir["files"] if f["path"].startswith("VT_")][0]
    fit_rows = []
    for s in base_file["sheets"]:
        for t in s["tables"]:
            if t["tag"] == "~FI_T":
                fit_rows.extend(t["rows"])

    # Find the trade efficiency row
    trade_eff_rows = [r for r in fit_rows if r.get("process") == "T_B_ELC_REG1_REG2_01"
                      and r.get("eff") == 0.95]
    assert len(trade_eff_rows) == 1
    assert trade_eff_rows[0]["region"] == "REG1"
    assert trade_eff_rows[0]["commodity-out"] == "ELC"


def test_trade_link_no_efficiency():
    """Trade links without efficiency should not emit ~FI_T rows."""
    source = {
        "model": {
            "name": "TradeNoEffTest",
            "regions": ["REG1", "REG2"],
            "commodities": [{"name": "ELC", "type": "energy"}],
            "processes": [
                {"name": "PP", "sets": ["ELE"], "primary_commodity_group": "NRGO"}
            ],
            "trade_links": [
                {
                    "origin": "REG1",
                    "destination": "REG2",
                    "commodity": "ELC",
                    "bidirectional": True,
                    # No efficiency specified
                },
            ],
        }
    }
    tableir = compile_vedalang_to_tableir(source)

    # Find trade file
    trade_files = [
        f for f in tableir["files"] if f["path"].startswith("SuppXLS/Trades/")
    ]
    assert len(trade_files) == 1

    # Should NOT have ~FI_T tables (only TradeLinks sheet)
    fit_tables = []
    for s in trade_files[0]["sheets"]:
        for t in s["tables"]:
            if t["tag"] == "~FI_T":
                fit_tables.append(t)

    assert len(fit_tables) == 0


def test_trade_links_emit_explicit_process_declarations():
    """Trade links should emit explicit ~FI_PROCESS declarations."""
    source = {
        "model": {
            "name": "TradeExplicitTest",
            "regions": ["REG1", "REG2"],
            "commodities": [{"name": "ELC", "type": "energy", "unit": "PJ"}],
            "processes": [
                {"name": "PP", "sets": ["ELE"], "primary_commodity_group": "NRGO"}
            ],
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
    tableir = compile_vedalang_to_tableir(source)

    # Find all ~FI_PROCESS rows
    process_rows = []
    for f in tableir["files"]:
        for s in f["sheets"]:
            for t in s["tables"]:
                if t["tag"] == "~FI_PROCESS":
                    process_rows.extend(t["rows"])

    # Trade process should be explicitly declared
    trade_proc_rows = [
        r for r in process_rows if r.get("process", "").startswith("T_")
    ]

    # Bidirectional = declared in BOTH regions
    assert len(trade_proc_rows) == 2
    regions = {r["region"] for r in trade_proc_rows}
    assert regions == {"REG1", "REG2"}

    # Should have IRE set
    for row in trade_proc_rows:
        assert row["sets"] == "IRE"
        assert row["process"] == "T_B_ELC_REG1_REG2_01"

    # Should also have topology in ~FI_T (commodity-in/out flows)
    topology_rows = []
    for f in tableir["files"]:
        for s in f["sheets"]:
            for t in s["tables"]:
                if t["tag"] == "~FI_T":
                    topology_rows.extend(t["rows"])

    trade_topo_rows = [
        r for r in topology_rows if r.get("process", "").startswith("T_")
    ]
    # One commodity-out (REG1), one commodity-in (REG2)
    assert len(trade_topo_rows) == 2

    # REG1 exports (commodity-out)
    out_row = [r for r in trade_topo_rows if r.get("commodity-out")]
    assert len(out_row) == 1
    assert out_row[0]["region"] == "REG1"
    assert out_row[0]["commodity-out"] == "ELC"

    # REG2 imports (commodity-in)
    in_row = [r for r in trade_topo_rows if r.get("commodity-in")]
    assert len(in_row) == 1
    assert in_row[0]["region"] == "REG2"
    assert in_row[0]["commodity-in"] == "ELC"


def test_trade_links_unidirectional_single_declaration():
    """Unidirectional trade should only declare process in origin region."""
    source = {
        "model": {
            "name": "TradeUniTest",
            "regions": ["REG1", "REG2"],
            "commodities": [{"name": "ELC", "type": "energy"}],
            "processes": [
                {"name": "PP", "sets": ["ELE"], "primary_commodity_group": "NRGO"}
            ],
            "trade_links": [
                {
                    "origin": "REG1",
                    "destination": "REG2",
                    "commodity": "ELC",
                    "bidirectional": False,
                },
            ],
        }
    }
    tableir = compile_vedalang_to_tableir(source)

    # Find all ~FI_PROCESS rows
    process_rows = []
    for f in tableir["files"]:
        for s in f["sheets"]:
            for t in s["tables"]:
                if t["tag"] == "~FI_PROCESS":
                    process_rows.extend(t["rows"])

    # Trade process should only be in origin (REG1)
    trade_proc_rows = [
        r for r in process_rows if r.get("process", "").startswith("T_")
    ]
    assert len(trade_proc_rows) == 1
    assert trade_proc_rows[0]["region"] == "REG1"
    assert trade_proc_rows[0]["process"] == "T_U_ELC_REG1_REG2_01"


# =============================================================================
# User Constraint Tests
# =============================================================================


def test_emission_cap_constraint():
    """emission_cap constraint should emit ~UC_T rows with UC_COMPRD and UC_RHSRT."""
    source = {
        "model": {
            "name": "EmissionCapTest",
            "regions": ["REG1"],
            "start_year": 2020,
            "time_periods": [10, 10],
            "commodities": [
                {"name": "CO2", "type": "emission"},
                {"name": "ELC", "type": "energy"},
            ],
            "processes": [
                {"name": "PP_CCGT", "sets": ["ELE"], "primary_commodity_group": "NRGO"},
            ],
            "constraints": [
                {
                    "name": "CO2_CAP",
                    "type": "emission_cap",
                    "commodity": "CO2",
                    "limit": 100,
                    "limtype": "up",
                },
            ],
        }
    }
    tableir = compile_vedalang_to_tableir(source)

    # Find ~UC_T table
    uc_rows = []
    for f in tableir["files"]:
        for s in f["sheets"]:
            for t in s["tables"]:
                if t["tag"] == "~UC_T":
                    uc_rows.extend(t["rows"])

    # Should have rows for 2 years (2020, 2030)
    # Each year: 1 uc_comprd row + 1 uc_rhs row = 2 rows
    assert len(uc_rows) == 4

    # Check uc_comprd rows (VedaOnline format: attribute as column header)
    comprd_rows = [r for r in uc_rows if "uc_comprd" in r]
    assert len(comprd_rows) == 2
    for row in comprd_rows:
        assert row["uc_n"] == "CO2_CAP"
        assert row["commodity"] == "CO2"
        assert row["side"] == "LHS"
        assert row["uc_comprd"] == 1

    # Check uc_rhs rows (VedaOnline format: attribute as column header)
    rhs_rows = [r for r in uc_rows if "uc_rhs" in r]
    assert len(rhs_rows) == 2
    for row in rhs_rows:
        assert row["uc_n"] == "CO2_CAP"
        assert row["limtype"] == "UP"
        assert row["uc_rhs"] == 100


def test_emission_cap_with_year_trajectory():
    """emission_cap with years dict should interpolate values."""
    source = {
        "model": {
            "name": "EmissionCapTrajectoryTest",
            "regions": ["REG1"],
            "start_year": 2020,
            "time_periods": [10, 10, 10],
            "commodities": [
                {"name": "CO2", "type": "emission"},
            ],
            "processes": [
                {"name": "PP", "sets": ["ELE"], "primary_commodity_group": "NRGO"}
            ],
            "constraints": [
                {
                    "name": "CO2_BUDGET",
                    "type": "emission_cap",
                    "commodity": "CO2",
                    "years": {
                        "2020": 100,
                        "2040": 50,
                    },
                    "interpolation": "interp_extrap",
                    "limtype": "up",
                },
            ],
        }
    }
    tableir = compile_vedalang_to_tableir(source)

    # Find ~UC_T rows
    uc_rows = []
    for f in tableir["files"]:
        for s in f["sheets"]:
            for t in s["tables"]:
                if t["tag"] == "~UC_T":
                    uc_rows.extend(t["rows"])

    # Check RHS values are interpolated (VedaOnline format: uc_rhs as column header)
    rhs_rows = [r for r in uc_rows if "uc_rhs" in r]
    by_year = {r["year"]: r["uc_rhs"] for r in rhs_rows}

    assert by_year[2020] == 100
    assert by_year[2030] == 75  # Interpolated
    assert by_year[2040] == 50


def test_activity_share_minimum():
    """activity_share with minimum_share should emit LO constraint."""
    source = {
        "model": {
            "name": "ActivityShareTest",
            "regions": ["REG1"],
            "start_year": 2020,
            "time_periods": [10],
            "commodities": [
                {"name": "ELC", "type": "energy"},
            ],
            "processes": [
                {"name": "PP_WIND", "sets": ["ELE"], "primary_commodity_group": "NRGO"},
                {
                    "name": "PP_SOLAR",
                    "sets": ["ELE"],
                    "primary_commodity_group": "NRGO",
                },
                {"name": "PP_CCGT", "sets": ["ELE"], "primary_commodity_group": "NRGO"},
            ],
            "constraints": [
                {
                    "name": "REN_TARGET",
                    "type": "activity_share",
                    "commodity": "ELC",
                    "processes": ["PP_WIND", "PP_SOLAR"],
                    "minimum_share": 0.30,
                },
            ],
        }
    }
    tableir = compile_vedalang_to_tableir(source)

    # Find ~UC_T rows
    uc_rows = []
    for f in tableir["files"]:
        for s in f["sheets"]:
            for t in s["tables"]:
                if t["tag"] == "~UC_T":
                    uc_rows.extend(t["rows"])

    # Should have rows for 1 year (2020):
    # 2 uc_act (PP_WIND, PP_SOLAR) + 1 uc_comprd + 1 uc_rhs = 4 rows
    assert len(uc_rows) == 4

    # Check uc_act rows (VedaOnline format: coefficient = 1 for target processes)
    act_rows = [r for r in uc_rows if "uc_act" in r]
    assert len(act_rows) == 2
    processes = {r["process"] for r in act_rows}
    assert processes == {"PP_WIND", "PP_SOLAR"}
    for row in act_rows:
        assert row["uc_act"] == 1
        assert row["side"] == "LHS"

    # Check uc_comprd row (VedaOnline format: coefficient = -share)
    comprd_rows = [r for r in uc_rows if "uc_comprd" in r]
    assert len(comprd_rows) == 1
    assert comprd_rows[0]["commodity"] == "ELC"
    assert comprd_rows[0]["uc_comprd"] == -0.30
    assert comprd_rows[0]["side"] == "LHS"

    # Check uc_rhs row (VedaOnline format: RHS = 0, limtype = LO)
    rhs_rows = [r for r in uc_rows if "uc_rhs" in r]
    assert len(rhs_rows) == 1
    assert rhs_rows[0]["uc_rhs"] == 0
    assert rhs_rows[0]["limtype"] == "LO"


def test_activity_share_maximum():
    """activity_share with maximum_share should emit UP constraint."""
    source = {
        "model": {
            "name": "ActivityShareMaxTest",
            "regions": ["REG1"],
            "start_year": 2020,
            "time_periods": [10],
            "commodities": [{"name": "ELC", "type": "energy"}],
            "processes": [
                {"name": "PP_COAL", "sets": ["ELE"], "primary_commodity_group": "NRGO"},
                {"name": "PP_CCGT", "sets": ["ELE"], "primary_commodity_group": "NRGO"},
            ],
            "constraints": [
                {
                    "name": "COAL_LIMIT",
                    "type": "activity_share",
                    "commodity": "ELC",
                    "processes": ["PP_COAL"],
                    "maximum_share": 0.20,
                },
            ],
        }
    }
    tableir = compile_vedalang_to_tableir(source)

    # Find ~UC_T rows
    uc_rows = []
    for f in tableir["files"]:
        for s in f["sheets"]:
            for t in s["tables"]:
                if t["tag"] == "~UC_T":
                    uc_rows.extend(t["rows"])

    # Check uc_rhs has limtype = UP (VedaOnline format)
    rhs_rows = [r for r in uc_rows if "uc_rhs" in r]
    assert len(rhs_rows) == 1
    assert rhs_rows[0]["limtype"] == "UP"

    # Check uc_comprd has -0.20 (VedaOnline format)
    comprd_rows = [r for r in uc_rows if "uc_comprd" in r]
    assert comprd_rows[0]["uc_comprd"] == -0.20


def test_activity_share_both_min_max():
    """activity_share with both min and max should emit two constraints."""
    source = {
        "model": {
            "name": "ActivityShareBothTest",
            "regions": ["REG1"],
            "start_year": 2020,
            "time_periods": [10],
            "commodities": [{"name": "ELC", "type": "energy"}],
            "processes": [
                {"name": "PP_WIND", "sets": ["ELE"], "primary_commodity_group": "NRGO"},
            ],
            "constraints": [
                {
                    "name": "WIND_BAND",
                    "type": "activity_share",
                    "commodity": "ELC",
                    "processes": ["PP_WIND"],
                    "minimum_share": 0.20,
                    "maximum_share": 0.40,
                },
            ],
        }
    }
    tableir = compile_vedalang_to_tableir(source)

    # Find ~UC_T rows
    uc_rows = []
    for f in tableir["files"]:
        for s in f["sheets"]:
            for t in s["tables"]:
                if t["tag"] == "~UC_T":
                    uc_rows.extend(t["rows"])

    # Should have 2 constraints (WIND_BAND_LO and WIND_BAND_UP)
    uc_names = {r["uc_n"] for r in uc_rows}
    assert uc_names == {"WIND_BAND_LO", "WIND_BAND_UP"}

    # Check LO constraint (VedaOnline format)
    lo_rhs = [
        r
        for r in uc_rows
        if r["uc_n"] == "WIND_BAND_LO" and "uc_rhs" in r
    ]
    assert len(lo_rhs) == 1
    assert lo_rhs[0]["limtype"] == "LO"

    lo_comprd = [
        r
        for r in uc_rows
        if r["uc_n"] == "WIND_BAND_LO" and "uc_comprd" in r
    ]
    assert lo_comprd[0]["uc_comprd"] == -0.20

    # Check UP constraint (VedaOnline format)
    up_rhs = [
        r
        for r in uc_rows
        if r["uc_n"] == "WIND_BAND_UP" and "uc_rhs" in r
    ]
    assert len(up_rhs) == 1
    assert up_rhs[0]["limtype"] == "UP"

    up_comprd = [
        r
        for r in uc_rows
        if r["uc_n"] == "WIND_BAND_UP" and "uc_comprd" in r
    ]
    assert up_comprd[0]["uc_comprd"] == -0.40


def test_constraint_file_path():
    """Constraints should be emitted to SuppXLS/Scen_UC_Constraints.xlsx."""
    source = {
        "model": {
            "name": "ConstraintFileTest",
            "regions": ["REG1"],
            "commodities": [{"name": "CO2", "type": "emission"}],
            "processes": [
                {"name": "PP", "sets": ["ELE"], "primary_commodity_group": "NRGO"}
            ],
            "constraints": [
                {
                    "name": "CO2_CAP",
                    "type": "emission_cap",
                    "commodity": "CO2",
                    "limit": 100,
                },
            ],
        }
    }
    tableir = compile_vedalang_to_tableir(source)

    # Find constraint file path
    constraint_files = [
        f["path"] for f in tableir["files"] if "UC_Constraints" in f["path"]
    ]
    assert len(constraint_files) == 1
    assert constraint_files[0] == "SuppXLS/Scen_UC_Constraints.xlsx"


# =============================================================================
# Primary Commodity Group (PCG) Tests
# =============================================================================


def test_pcg_missing_raises_validation_error():
    """Process without primary_commodity_group should raise ValidationError."""
    source = {
        "model": {
            "name": "PCGMissingTest",
            "regions": ["REG1"],
            "commodities": [
                {"name": "NG", "type": "energy"},
                {"name": "ELC", "type": "energy"},
            ],
            "processes": [
                {
                    "name": "PP_CCGT",
                    "sets": ["ELE"],
                    "inputs": [{"commodity": "NG"}],
                    "outputs": [{"commodity": "ELC"}],
                },
            ],
        }
    }
    with pytest.raises(jsonschema.ValidationError) as exc_info:
        compile_vedalang_to_tableir(source)
    assert "primary_commodity_group" in str(exc_info.value)


def test_pcg_invalid_value_raises_validation_error():
    """Process with invalid primary_commodity_group should raise ValidationError."""
    source = {
        "model": {
            "name": "PCGInvalidTest",
            "regions": ["REG1"],
            "commodities": [
                {"name": "ELC", "type": "energy"},
            ],
            "processes": [
                {
                    "name": "PP_CCGT",
                    "sets": ["ELE"],
                    "primary_commodity_group": "INVALID",
                    "outputs": [{"commodity": "ELC"}],
                },
            ],
        }
    }
    with pytest.raises(jsonschema.ValidationError) as exc_info:
        compile_vedalang_to_tableir(source)
    assert "INVALID" in str(exc_info.value)


def test_pcg_explicit_nrgo():
    """Explicit primary_commodity_group=NRGO should compile correctly."""
    source = {
        "model": {
            "name": "PCGExplicitTest",
            "regions": ["REG1"],
            "commodities": [
                {"name": "NG", "type": "energy"},
                {"name": "ELC", "type": "energy"},
            ],
            "processes": [
                {
                    "name": "PP_CCGT",
                    "sets": ["ELE"],
                    "primary_commodity_group": "NRGO",
                    "inputs": [{"commodity": "NG"}],
                    "outputs": [{"commodity": "ELC"}],
                },
            ],
        }
    }
    tableir = compile_vedalang_to_tableir(source)

    process_rows = []
    for f in tableir["files"]:
        for s in f["sheets"]:
            for t in s["tables"]:
                if t["tag"] == "~FI_PROCESS":
                    process_rows.extend(t["rows"])

    ccgt = [r for r in process_rows if r["process"] == "PP_CCGT"][0]
    assert ccgt["primarycg"] == "NRGO"


def test_pcg_explicit_demo():
    """Explicit primary_commodity_group=DEMO should compile correctly."""
    source = {
        "model": {
            "name": "PCGDemoTest",
            "regions": ["REG1"],
            "commodities": [
                {"name": "ELC", "type": "energy"},
                {"name": "RSD", "type": "demand"},
            ],
            "processes": [
                {
                    "name": "DEM_RSD",
                    "sets": ["DMD"],
                    "primary_commodity_group": "DEMO",
                    "inputs": [{"commodity": "ELC"}],
                    "outputs": [{"commodity": "RSD"}],
                },
            ],
        }
    }
    tableir = compile_vedalang_to_tableir(source)

    process_rows = []
    for f in tableir["files"]:
        for s in f["sheets"]:
            for t in s["tables"]:
                if t["tag"] == "~FI_PROCESS":
                    process_rows.extend(t["rows"])

    dem = [r for r in process_rows if r["process"] == "DEM_RSD"][0]
    assert dem["primarycg"] == "DEMO"


def test_pcg_always_emitted():
    """primarycg column should always be emitted in ~FI_PROCESS."""
    source = load_vedalang(EXAMPLES_DIR / "mini_plant.veda.yaml")
    tableir = compile_vedalang_to_tableir(source)

    # Find ~FI_PROCESS rows
    process_rows = []
    for f in tableir["files"]:
        for s in f["sheets"]:
            for t in s["tables"]:
                if t["tag"] == "~FI_PROCESS":
                    process_rows.extend(t["rows"])

    # All process rows should have primarycg
    valid_pcgs = [
        "DEMI",
        "DEMO",
        "MATI",
        "MATO",
        "NRGI",
        "NRGO",
        "ENVI",
        "ENVO",
        "FINI",
        "FINO",
    ]
    for row in process_rows:
        assert "primarycg" in row, f"Process {row.get('process')} missing primarycg"
        assert row["primarycg"] in valid_pcgs


def test_no_constraints_when_not_defined():
    """Models without constraints should not emit UC file."""
    source = load_vedalang(EXAMPLES_DIR / "mini_plant.veda.yaml")
    tableir = compile_vedalang_to_tableir(source)

    # Should NOT have UC file
    for f in tableir["files"]:
        assert "UC_Constraints" not in f["path"]
        for s in f["sheets"]:
            for t in s["tables"]:
                assert t["tag"] != "~UC_T"


def test_emission_cap_lower_bound():
    """emission_cap with limtype='lo' should set LO limit."""
    source = {
        "model": {
            "name": "EmissionMinTest",
            "regions": ["REG1"],
            "commodities": [{"name": "CO2", "type": "emission"}],
            "processes": [
                {"name": "PP", "sets": ["ELE"], "primary_commodity_group": "NRGO"}
            ],
            "constraints": [
                {
                    "name": "CO2_MIN",
                    "type": "emission_cap",
                    "commodity": "CO2",
                    "limit": 50,
                    "limtype": "lo",
                },
            ],
        }
    }
    tableir = compile_vedalang_to_tableir(source)

    # Find ~UC_T rows
    uc_rows = []
    for f in tableir["files"]:
        for s in f["sheets"]:
            for t in s["tables"]:
                if t["tag"] == "~UC_T":
                    uc_rows.extend(t["rows"])

    # Check limtype is LO (VedaOnline format)
    rhs_rows = [r for r in uc_rows if "uc_rhs" in r]
    assert all(r["limtype"] == "LO" for r in rhs_rows)


def test_uc_table_has_uc_sets_metadata():
    """~UC_T tables should include uc_sets metadata for xl2times processing."""
    source = {
        "model": {
            "name": "UCSetTest",
            "regions": ["REG1"],
            "commodities": [{"name": "CO2", "type": "emission"}],
            "processes": [
                {"name": "PP", "sets": ["ELE"], "primary_commodity_group": "NRGO"}
            ],
            "constraints": [
                {
                    "name": "CO2_CAP",
                    "type": "emission_cap",
                    "commodity": "CO2",
                    "limit": 100,
                },
            ],
        }
    }
    tableir = compile_vedalang_to_tableir(source)

    # Find ~UC_T table and check it has uc_sets
    uc_table = None
    for f in tableir["files"]:
        for s in f["sheets"]:
            for t in s["tables"]:
                if t["tag"] == "~UC_T":
                    uc_table = t
                    break

    assert uc_table is not None, "Should have ~UC_T table"
    assert "uc_sets" in uc_table, "~UC_T table should have uc_sets"
    assert "R_E" in uc_table["uc_sets"], "Should have R_E scope"
    assert "T_E" in uc_table["uc_sets"], "Should have T_E scope"
    assert uc_table["uc_sets"]["R_E"] == "AllRegions"
    assert uc_table["uc_sets"]["T_E"] == ""


# =============================================================================
# Semantic Cross-Reference Validation Tests
# =============================================================================


def test_unknown_commodity_in_process_input():
    """Unknown commodity in process inputs should raise SemanticValidationError."""
    source = {
        "model": {
            "name": "BadInputTest",
            "regions": ["REG1"],
            "commodities": [
                {"name": "ELC", "type": "energy"},
            ],
            "processes": [
                {
                    "name": "PP_CCGT",
                    "sets": ["ELE"],
                    "primary_commodity_group": "NRGO",
                    "inputs": [{"commodity": "NG_MISSING"}],
                    "outputs": [{"commodity": "ELC"}],
                },
            ],
        }
    }
    with pytest.raises(SemanticValidationError) as exc_info:
        compile_vedalang_to_tableir(source)
    assert "NG_MISSING" in str(exc_info.value)
    assert "PP_CCGT" in str(exc_info.value)
    assert "inputs[0]" in str(exc_info.value)


def test_unknown_commodity_in_process_output():
    """Unknown commodity in process outputs should raise SemanticValidationError."""
    source = {
        "model": {
            "name": "BadOutputTest",
            "regions": ["REG1"],
            "commodities": [
                {"name": "NG", "type": "energy"},
            ],
            "processes": [
                {
                    "name": "PP_CCGT",
                    "sets": ["ELE"],
                    "primary_commodity_group": "NRGO",
                    "inputs": [{"commodity": "NG"}],
                    "outputs": [{"commodity": "ELC1"}],
                },
            ],
        }
    }
    with pytest.raises(SemanticValidationError) as exc_info:
        compile_vedalang_to_tableir(source)
    assert "ELC1" in str(exc_info.value)
    assert "PP_CCGT" in str(exc_info.value)
    assert "outputs[0]" in str(exc_info.value)


def test_unknown_commodity_suggests_similar():
    """Unknown commodity should suggest similar commodity name."""
    source = {
        "model": {
            "name": "SuggestTest",
            "regions": ["REG1"],
            "commodities": [
                {"name": "ELC", "type": "energy"},
            ],
            "processes": [
                {
                    "name": "PP_CCGT",
                    "sets": ["ELE"],
                    "primary_commodity_group": "NRGO",
                    "outputs": [{"commodity": "EL"}],
                },
            ],
        }
    }
    with pytest.raises(SemanticValidationError) as exc_info:
        compile_vedalang_to_tableir(source)
    assert "Did you mean 'ELC'" in str(exc_info.value)


def test_unknown_process_in_constraint():
    """Unknown process in constraint should raise SemanticValidationError."""
    source = {
        "model": {
            "name": "BadConstraintTest",
            "regions": ["REG1"],
            "commodities": [
                {"name": "ELC", "type": "energy"},
            ],
            "processes": [
                {
                    "name": "PP_CCGT",
                    "sets": ["ELE"],
                    "primary_commodity_group": "NRGO",
                    "outputs": [{"commodity": "ELC"}],
                },
            ],
            "constraints": [
                {
                    "name": "REN_TARGET",
                    "type": "activity_share",
                    "commodity": "ELC",
                    "processes": ["PP_WIND_MISSING"],
                    "minimum_share": 0.30,
                },
            ],
        }
    }
    with pytest.raises(SemanticValidationError) as exc_info:
        compile_vedalang_to_tableir(source)
    assert "PP_WIND_MISSING" in str(exc_info.value)
    assert "REN_TARGET" in str(exc_info.value)


def test_unknown_region_in_trade_link():
    """Unknown region in trade_link should raise SemanticValidationError."""
    source = {
        "model": {
            "name": "BadTradeTest",
            "regions": ["REG1", "REG2"],
            "commodities": [
                {"name": "ELC", "type": "energy"},
            ],
            "processes": [
                {
                    "name": "PP_CCGT",
                    "sets": ["ELE"],
                    "primary_commodity_group": "NRGO",
                    "outputs": [{"commodity": "ELC"}],
                },
            ],
            "trade_links": [
                {
                    "origin": "REG1",
                    "destination": "REG3_MISSING",
                    "commodity": "ELC",
                },
            ],
        }
    }
    with pytest.raises(SemanticValidationError) as exc_info:
        compile_vedalang_to_tableir(source)
    assert "REG3_MISSING" in str(exc_info.value)
    assert "destination" in str(exc_info.value)


def test_unknown_commodity_in_trade_link():
    """Unknown commodity in trade_link should raise SemanticValidationError."""
    source = {
        "model": {
            "name": "BadTradeCommTest",
            "regions": ["REG1", "REG2"],
            "commodities": [
                {"name": "ELC", "type": "energy"},
            ],
            "processes": [
                {
                    "name": "PP_CCGT",
                    "sets": ["ELE"],
                    "primary_commodity_group": "NRGO",
                    "outputs": [{"commodity": "ELC"}],
                },
            ],
            "trade_links": [
                {
                    "origin": "REG1",
                    "destination": "REG2",
                    "commodity": "GAS_MISSING",
                },
            ],
        }
    }
    with pytest.raises(SemanticValidationError) as exc_info:
        compile_vedalang_to_tableir(source)
    assert "GAS_MISSING" in str(exc_info.value)


def test_demand_projection_wrong_commodity_type():
    """demand_projection targeting non-demand commodity should raise error."""
    source = {
        "model": {
            "name": "BadDemandTest",
            "regions": ["REG1"],
            "commodities": [
                {"name": "NG", "type": "energy"},
            ],
            "processes": [
                {
                    "name": "IMP_NG",
                    "sets": ["IMP"],
                    "primary_commodity_group": "NRGO",
                    "outputs": [{"commodity": "NG"}],
                },
            ],
            "scenarios": [
                {
                    "name": "BaseDemand",
                    "type": "demand_projection",
                    "commodity": "NG",
                    "interpolation": "interp_extrap",
                    "values": {"2020": 100.0},
                },
            ],
        }
    }
    with pytest.raises(SemanticValidationError) as exc_info:
        compile_vedalang_to_tableir(source)
    assert "demand_projection" in str(exc_info.value)
    assert "BaseDemand" in str(exc_info.value)
    assert "NG" in str(exc_info.value)
    assert "energy" in str(exc_info.value)


def test_commodity_price_wrong_commodity_type():
    """commodity_price targeting demand commodity should raise error."""
    source = {
        "model": {
            "name": "BadPriceTest",
            "regions": ["REG1"],
            "commodities": [
                {"name": "RSD", "type": "demand"},
            ],
            "processes": [
                {
                    "name": "DEM_RSD",
                    "sets": ["DMD"],
                    "primary_commodity_group": "DEMO",
                    "outputs": [{"commodity": "RSD"}],
                },
            ],
            "scenarios": [
                {
                    "name": "DemandPrice",
                    "type": "commodity_price",
                    "commodity": "RSD",
                    "interpolation": "interp_extrap",
                    "values": {"2020": 100.0},
                },
            ],
        }
    }
    with pytest.raises(SemanticValidationError) as exc_info:
        compile_vedalang_to_tableir(source)
    assert "commodity_price" in str(exc_info.value)
    assert "DemandPrice" in str(exc_info.value)
    assert "demand" in str(exc_info.value)


def test_unit_warning_for_unusual_activity_unit():
    """Non-energy activity_unit should generate warning."""
    model = {
        "name": "UnitWarningTest",
        "regions": ["REG1"],
        "commodities": [{"name": "ELC", "type": "energy"}],
        "processes": [
            {
                "name": "PP_CCGT",
                "sets": ["ELE"],
                "primary_commodity_group": "NRGO",
                "activity_unit": "kg",
                "outputs": [{"commodity": "ELC"}],
            },
        ],
    }
    errors, warnings = validate_cross_references(model)
    assert len(errors) == 0
    assert len(warnings) == 1
    assert "kg" in warnings[0]
    assert "PP_CCGT" in warnings[0]
    assert "activity_unit" in warnings[0]


def test_unit_warning_for_unusual_capacity_unit():
    """Non-power capacity_unit should generate warning."""
    model = {
        "name": "CapUnitWarningTest",
        "regions": ["REG1"],
        "commodities": [{"name": "ELC", "type": "energy"}],
        "processes": [
            {
                "name": "PP_CCGT",
                "sets": ["ELE"],
                "primary_commodity_group": "NRGO",
                "capacity_unit": "Mt",
                "outputs": [{"commodity": "ELC"}],
            },
        ],
    }
    errors, warnings = validate_cross_references(model)
    assert len(errors) == 0
    assert len(warnings) == 1
    assert "Mt" in warnings[0]
    assert "capacity_unit" in warnings[0]


def test_multiple_errors_collected():
    """Multiple errors should be collected, not fail-fast."""
    source = {
        "model": {
            "name": "MultiErrorTest",
            "regions": ["REG1"],
            "commodities": [
                {"name": "ELC", "type": "energy"},
            ],
            "processes": [
                {
                    "name": "PP_CCGT",
                    "sets": ["ELE"],
                    "primary_commodity_group": "NRGO",
                    "inputs": [{"commodity": "MISSING1"}],
                    "outputs": [{"commodity": "MISSING2"}],
                },
            ],
        }
    }
    with pytest.raises(SemanticValidationError) as exc_info:
        compile_vedalang_to_tableir(source)
    assert "MISSING1" in str(exc_info.value)
    assert "MISSING2" in str(exc_info.value)
    assert len(exc_info.value.errors) == 2


def test_all_examples_pass_semantic_validation():
    """All example files should pass semantic validation."""
    example_files = list(EXAMPLES_DIR.glob("*.veda.yaml"))
    assert len(example_files) > 0, "Should have example files"

    for example_file in example_files:
        source = load_vedalang(example_file)
        tableir = compile_vedalang_to_tableir(source)
        assert "files" in tableir, f"Failed for {example_file.name}"


# =============================================================================
# Time-Varying Process Attributes Tests
# =============================================================================


def test_time_varying_invcost():
    """Time-varying invcost should emit year-indexed rows with canonical column name."""
    source = {
        "model": {
            "name": "TimeVaryTest",
            "regions": ["REG1"],
            "commodities": [{"name": "ELC", "type": "energy"}],
            "processes": [
                {
                    "name": "SolarPV",
                    "sets": ["ELE"],
                    "primary_commodity_group": "NRGO",
                    "outputs": [{"commodity": "ELC"}],
                    "invcost": {"values": {"2020": 1000, "2030": 600, "2050": 300}},
                }
            ],
        }
    }
    tableir = compile_vedalang_to_tableir(source)

    # Find ~FI_T rows for SolarPV
    fit_rows = []
    for f in tableir["files"]:
        for s in f.get("sheets", []):
            for t in s.get("tables", []):
                if t["tag"] == "~FI_T":
                    fit_rows.extend(
                        r for r in t["rows"] if r.get("process") == "SolarPV"
                    )

    # Should have rows with year column for ncap_cost (canonical for invcost)
    ncap_cost_rows = [r for r in fit_rows if "ncap_cost" in r and "year" in r]
    assert len(ncap_cost_rows) == 4  # year=0 (interp) + 3 data years

    # Check interpolation row (year=0)
    interp_row = [r for r in ncap_cost_rows if r["year"] == 0][0]
    assert interp_row["ncap_cost"] == 3  # interp_extrap code

    # Check data rows
    years_values = {r["year"]: r["ncap_cost"] for r in ncap_cost_rows if r["year"] > 0}
    assert years_values[2020] == 1000
    assert years_values[2030] == 600
    assert years_values[2050] == 300


def test_time_varying_efficiency():
    """Time-varying efficiency should emit year-indexed rows."""
    source = {
        "model": {
            "name": "TimeVaryTest",
            "regions": ["REG1"],
            "commodities": [
                {"name": "NG", "type": "energy"},
                {"name": "ELC", "type": "energy"},
            ],
            "processes": [
                {
                    "name": "CCGT",
                    "sets": ["ELE"],
                    "primary_commodity_group": "NRGO",
                    "inputs": [{"commodity": "NG"}],
                    "outputs": [{"commodity": "ELC"}],
                    "efficiency": {
                        "values": {"2020": 0.55, "2030": 0.60, "2050": 0.65},
                        "interpolation": "interp_extrap",
                    },
                }
            ],
        }
    }
    tableir = compile_vedalang_to_tableir(source)

    # Find ~FI_T rows
    fit_rows = []
    for f in tableir["files"]:
        for s in f.get("sheets", []):
            for t in s.get("tables", []):
                if t["tag"] == "~FI_T":
                    fit_rows.extend(r for r in t["rows"] if r.get("process") == "CCGT")

    # Should have rows with year column for eff
    eff_rows = [r for r in fit_rows if "eff" in r and "year" in r]
    assert len(eff_rows) == 4  # year=0 + 3 data years

    years_values = {r["year"]: r["eff"] for r in eff_rows if r["year"] > 0}
    assert years_values[2020] == 0.55
    assert years_values[2030] == 0.60
    assert years_values[2050] == 0.65


def test_time_varying_mixed_with_scalar():
    """Time-varying and scalar attributes can coexist."""
    source = {
        "model": {
            "name": "MixedTest",
            "regions": ["REG1"],
            "commodities": [{"name": "ELC", "type": "energy"}],
            "processes": [
                {
                    "name": "Wind",
                    "sets": ["ELE"],
                    "primary_commodity_group": "NRGO",
                    "outputs": [{"commodity": "ELC"}],
                    "invcost": {"values": {"2020": 1500, "2030": 1000}},
                    "life": 25,  # Scalar
                    "fixom": 30,  # Scalar
                }
            ],
        }
    }
    tableir = compile_vedalang_to_tableir(source)

    fit_rows = []
    for f in tableir["files"]:
        for s in f.get("sheets", []):
            for t in s.get("tables", []):
                if t["tag"] == "~FI_T":
                    fit_rows.extend(r for r in t["rows"] if r.get("process") == "Wind")

    # Should have year-indexed ncap_cost rows (canonical for invcost)
    ncap_cost_rows = [r for r in fit_rows if "ncap_cost" in r and "year" in r]
    assert len(ncap_cost_rows) == 3  # year=0 + 2 data years

    # Should have a row with scalar ncap_tlife and ncap_fom (merged)
    # Using canonical names: life->ncap_tlife, fixom->ncap_fom
    scalar_rows = [r for r in fit_rows if "ncap_tlife" in r or "ncap_fom" in r]
    assert len(scalar_rows) >= 1
    # At least one row should have both
    row_with_both = [r for r in scalar_rows if "ncap_tlife" in r and "ncap_fom" in r]
    assert len(row_with_both) >= 1
    assert row_with_both[0]["ncap_tlife"] == 25
    assert row_with_both[0]["ncap_fom"] == 30


def test_time_varying_no_interpolation():
    """Interpolation mode 'none' should not emit year=0 row."""
    source = {
        "model": {
            "name": "NoInterpTest",
            "regions": ["REG1"],
            "commodities": [{"name": "ELC", "type": "energy"}],
            "processes": [
                {
                    "name": "Coal",
                    "sets": ["ELE"],
                    "primary_commodity_group": "NRGO",
                    "outputs": [{"commodity": "ELC"}],
                    "invcost": {
                        "values": {"2020": 2000, "2030": 2100},
                        "interpolation": "none",
                    },
                }
            ],
        }
    }
    tableir = compile_vedalang_to_tableir(source)

    fit_rows = []
    for f in tableir["files"]:
        for s in f.get("sheets", []):
            for t in s.get("tables", []):
                if t["tag"] == "~FI_T":
                    fit_rows.extend(r for r in t["rows"] if r.get("process") == "Coal")

    ncap_cost_rows = [r for r in fit_rows if "ncap_cost" in r and "year" in r]
    # Should only have 2 rows (no year=0 for interpolation)
    assert len(ncap_cost_rows) == 2
    years = [r["year"] for r in ncap_cost_rows]
    assert 0 not in years
    assert 2020 in years
    assert 2030 in years


# =============================================================================
# Ergonomic Features Tests
# =============================================================================


def test_single_input_string_shorthand():
    """Single input can be specified as string instead of array."""
    source = {
        "model": {
            "name": "ShorthandInputTest",
            "regions": ["REG1"],
            "commodities": [
                {"name": "NG", "type": "energy"},
                {"name": "ELC", "type": "energy"},
            ],
            "processes": [
                {
                    "name": "PP_CCGT",
                    "sets": ["ELE"],
                    "primary_commodity_group": "NRGO",
                    "input": "NG",  # Shorthand instead of inputs array
                    "outputs": [{"commodity": "ELC"}],
                    "efficiency": 0.55,
                },
            ],
        }
    }
    tableir = compile_vedalang_to_tableir(source)

    # Find ~FI_T rows
    fit_rows = []
    for f in tableir["files"]:
        for s in f["sheets"]:
            for t in s["tables"]:
                if t["tag"] == "~FI_T":
                    fit_rows.extend(t["rows"])

    # Should have input row for NG
    input_rows = [r for r in fit_rows if r.get("commodity-in") == "NG"]
    assert len(input_rows) == 1
    assert input_rows[0]["process"] == "PP_CCGT"


def test_single_output_string_shorthand():
    """Single output can be specified as string instead of array."""
    source = {
        "model": {
            "name": "ShorthandOutputTest",
            "regions": ["REG1"],
            "commodities": [
                {"name": "NG", "type": "energy"},
                {"name": "ELC", "type": "energy"},
            ],
            "processes": [
                {
                    "name": "PP_CCGT",
                    "sets": ["ELE"],
                    "primary_commodity_group": "NRGO",
                    "inputs": [{"commodity": "NG"}],
                    "output": "ELC",  # Shorthand instead of outputs array
                    "efficiency": 0.55,
                },
            ],
        }
    }
    tableir = compile_vedalang_to_tableir(source)

    # Find ~FI_T rows
    fit_rows = []
    for f in tableir["files"]:
        for s in f["sheets"]:
            for t in s["tables"]:
                if t["tag"] == "~FI_T":
                    fit_rows.extend(t["rows"])

    # Should have output row for ELC
    output_rows = [r for r in fit_rows if r.get("commodity-out") == "ELC"]
    assert len(output_rows) >= 1


def test_both_input_output_shorthand():
    """Both input and output can use string shorthand."""
    source = {
        "model": {
            "name": "BothShorthandTest",
            "regions": ["REG1"],
            "commodities": [
                {"name": "NG", "type": "energy"},
                {"name": "ELC", "type": "energy"},
            ],
            "processes": [
                {
                    "name": "PP_CCGT",
                    "sets": ["ELE"],
                    "primary_commodity_group": "NRGO",
                    "input": "NG",  # Shorthand
                    "output": "ELC",  # Shorthand
                    "efficiency": 0.55,
                },
            ],
        }
    }
    tableir = compile_vedalang_to_tableir(source)

    # Find ~FI_T rows
    fit_rows = []
    for f in tableir["files"]:
        for s in f["sheets"]:
            for t in s["tables"]:
                if t["tag"] == "~FI_T":
                    fit_rows.extend(t["rows"])

    # Should have both input and output
    input_rows = [r for r in fit_rows if r.get("commodity-in") == "NG"]
    output_rows = [r for r in fit_rows if r.get("commodity-out") == "ELC"]
    assert len(input_rows) == 1
    assert len(output_rows) >= 1


def test_default_commodity_units_energy():
    """Energy commodities default to PJ unit."""
    source = {
        "model": {
            "name": "DefaultUnitTest",
            "regions": ["REG1"],
            "commodities": [
                {"name": "ELC", "type": "energy"},  # No unit specified
            ],
            "processes": [
                {
                    "name": "PP_CCGT",
                    "sets": ["ELE"],
                    "primary_commodity_group": "NRGO",
                    "output": "ELC",
                },
            ],
        }
    }
    tableir = compile_vedalang_to_tableir(source)

    # Find ~FI_COMM rows
    comm_rows = []
    for f in tableir["files"]:
        for s in f["sheets"]:
            for t in s["tables"]:
                if t["tag"] == "~FI_COMM":
                    comm_rows.extend(t["rows"])

    # ELC should have default unit PJ
    elc_row = [r for r in comm_rows if r["commodity"] == "ELC"][0]
    assert elc_row["unit"] == "PJ"


def test_default_commodity_units_emission():
    """Emission commodities default to Mt unit."""
    source = {
        "model": {
            "name": "EmissionUnitTest",
            "regions": ["REG1"],
            "commodities": [
                {"name": "CO2", "type": "emission"},  # No unit specified
                {"name": "ELC", "type": "energy"},
            ],
            "processes": [
                {
                    "name": "PP_CCGT",
                    "sets": ["ELE"],
                    "primary_commodity_group": "NRGO",
                    "output": "ELC",
                },
            ],
        }
    }
    tableir = compile_vedalang_to_tableir(source)

    # Find ~FI_COMM rows
    comm_rows = []
    for f in tableir["files"]:
        for s in f["sheets"]:
            for t in s["tables"]:
                if t["tag"] == "~FI_COMM":
                    comm_rows.extend(t["rows"])

    # CO2 should have default unit Mt
    co2_row = [r for r in comm_rows if r["commodity"] == "CO2"][0]
    assert co2_row["unit"] == "Mt"


def test_default_commodity_units_demand():
    """Demand commodities default to PJ unit."""
    source = {
        "model": {
            "name": "DemandUnitTest",
            "regions": ["REG1"],
            "commodities": [
                {"name": "RSD", "type": "demand"},  # No unit specified
                {"name": "ELC", "type": "energy"},
            ],
            "processes": [
                {
                    "name": "DMD_RSD",
                    "sets": ["DMD"],
                    "primary_commodity_group": "DEMO",
                    "input": "ELC",
                    "output": "RSD",
                },
            ],
        }
    }
    tableir = compile_vedalang_to_tableir(source)

    # Find ~FI_COMM rows
    comm_rows = []
    for f in tableir["files"]:
        for s in f["sheets"]:
            for t in s["tables"]:
                if t["tag"] == "~FI_COMM":
                    comm_rows.extend(t["rows"])

    # RSD should have default unit PJ
    rsd_row = [r for r in comm_rows if r["commodity"] == "RSD"][0]
    assert rsd_row["unit"] == "PJ"


def test_default_commodity_units_material():
    """Material commodities default to Mt unit."""
    source = {
        "model": {
            "name": "MaterialUnitTest",
            "regions": ["REG1"],
            "commodities": [
                {"name": "H2", "type": "material"},  # No unit specified
                {"name": "ELC", "type": "energy"},
            ],
            "processes": [
                {
                    "name": "PP_ELYZ",
                    "sets": ["ELE"],
                    "primary_commodity_group": "MATO",
                    "input": "ELC",
                    "output": "H2",
                },
            ],
        }
    }
    tableir = compile_vedalang_to_tableir(source)

    # Find ~FI_COMM rows
    comm_rows = []
    for f in tableir["files"]:
        for s in f["sheets"]:
            for t in s["tables"]:
                if t["tag"] == "~FI_COMM":
                    comm_rows.extend(t["rows"])

    # H2 should have default unit Mt
    h2_row = [r for r in comm_rows if r["commodity"] == "H2"][0]
    assert h2_row["unit"] == "Mt"


def test_explicit_unit_overrides_default():
    """Explicitly specified unit should override default."""
    source = {
        "model": {
            "name": "ExplicitUnitTest",
            "regions": ["REG1"],
            "commodities": [
                {"name": "ELC", "type": "energy", "unit": "TWh"},  # Explicit unit
            ],
            "processes": [
                {
                    "name": "PP_CCGT",
                    "sets": ["ELE"],
                    "primary_commodity_group": "NRGO",
                    "output": "ELC",
                },
            ],
        }
    }
    tableir = compile_vedalang_to_tableir(source)

    # Find ~FI_COMM rows
    comm_rows = []
    for f in tableir["files"]:
        for s in f["sheets"]:
            for t in s["tables"]:
                if t["tag"] == "~FI_COMM":
                    comm_rows.extend(t["rows"])

    # ELC should have explicit unit TWh
    elc_row = [r for r in comm_rows if r["commodity"] == "ELC"][0]
    assert elc_row["unit"] == "TWh"


def test_shorthand_validation_unknown_commodity():
    """Unknown commodity in shorthand syntax should raise SemanticValidationError."""
    source = {
        "model": {
            "name": "BadShorthandTest",
            "regions": ["REG1"],
            "commodities": [
                {"name": "ELC", "type": "energy"},
            ],
            "processes": [
                {
                    "name": "PP_CCGT",
                    "sets": ["ELE"],
                    "primary_commodity_group": "NRGO",
                    "input": "MISSING_NG",  # Unknown commodity in shorthand
                    "output": "ELC",
                },
            ],
        }
    }
    with pytest.raises(SemanticValidationError) as exc_info:
        compile_vedalang_to_tableir(source)
    assert "MISSING_NG" in str(exc_info.value)
    assert "PP_CCGT" in str(exc_info.value)
