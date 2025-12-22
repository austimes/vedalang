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

    # Find the cost row for PP_CCGT (has eff, invcost, fixom, varom, life)
    ccgt_cost_rows = [
        r for r in fit_rows if r.get("techname") == "PP_CCGT" and "eff" in r
    ]
    assert len(ccgt_cost_rows) == 1
    ccgt_row = ccgt_cost_rows[0]
    assert ccgt_row["eff"] == 0.55
    assert ccgt_row["invcost"] == 800
    assert ccgt_row["fixom"] == 20
    assert ccgt_row["varom"] == 2
    assert ccgt_row["life"] == 30

    # Find the cost row for IMP_NG (cost merged into commodity-out row)
    imp_cost_rows = [
        r for r in fit_rows if r.get("techname") == "IMP_NG" and "cost" in r
    ]
    assert len(imp_cost_rows) == 1
    assert imp_cost_rows[0]["cost"] == 5.0
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

    # Find demand projection rows
    demand_rows = [r for r in fit_rows if r.get("attribute") == "DEMAND"]

    # Should have 4 rows (one per model year: 2020, 2030, 2040, 2050)
    assert len(demand_rows) == 4

    # Check years are present
    years = sorted([r["year"] for r in demand_rows])
    assert years == [2020, 2030, 2040, 2050]

    # Check commodity is correct
    for row in demand_rows:
        assert row["commodity"] == "RSD"
        assert row["region"] == "REG1"

    # Check values are interpolated correctly
    values_by_year = {r["year"]: r["value"] for r in demand_rows}
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
    assert cap_up[0]["techname"] == "PP_CCGT"

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
        r for r in bound_rows
        if r.get("techname") == "PP_CCGT" and r.get("cap_bnd") == 10.0
    ]
    assert len(ccgt_cap_up) == 1

    wind_cap_lo = [
        r for r in bound_rows
        if r.get("techname") == "PP_WIND" and r.get("limtype") == "LO"
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
            "processes": [{"name": "PP_CCGT", "sets": ["ELE"]}],
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

    # Find ~TRADELINKS tables
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

    # Check bidirectional ELC link (matrix format)
    bi_elc_idx = sheet_names.index("Bi_ELC")
    elc_rows = tradelinks_tables[bi_elc_idx]["rows"]
    assert len(elc_rows) == 1  # One origin
    assert elc_rows[0]["ELC"] == "REG1"  # First column is commodity, value is origin
    assert elc_rows[0]["REG2"] == 1  # Destination column has 1

    # Check unidirectional NG link
    uni_ng_idx = sheet_names.index("Uni_NG")
    ng_rows = tradelinks_tables[uni_ng_idx]["rows"]
    assert len(ng_rows) == 1
    assert ng_rows[0]["NG"] == "REG1"
    assert ng_rows[0]["REG2"] == 1


def test_trade_links_file_path():
    """Trade links should be in SuppXLS/Trades directory."""
    source = {
        "model": {
            "name": "TestModel",
            "regions": ["REG1", "REG2"],
            "commodities": [{"name": "ELC", "type": "energy"}],
            "processes": [{"name": "PP", "sets": ["ELE"]}],
            "trade_links": [
                {"origin": "REG1", "destination": "REG2", "commodity": "ELC"},
            ],
        }
    }
    tableir = compile_vedalang_to_tableir(source)

    # Find trade file path (in SuppXLS/Trades)
    trade_files = [
        f["path"] for f in tableir["files"]
        if f["path"].startswith("SuppXLS/Trades/")
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
        f for f in tableir["files"]
        if f["path"].startswith("SuppXLS/Trades/")
    ]
    assert len(trade_files) == 1

    # Should have ~TRADELINKS tables (2 sheets for 2 commodities)
    trade_sheets = trade_files[0]["sheets"]
    assert len(trade_sheets) == 2
    for s in trade_sheets:
        for t in s["tables"]:
            assert t["tag"] == "~TRADELINKS"
