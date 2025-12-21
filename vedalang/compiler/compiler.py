"""VedaLang to TableIR compiler."""

import json
from pathlib import Path

import jsonschema
import yaml

SCHEMA_DIR = Path(__file__).parent.parent / "schema"


def load_vedalang_schema() -> dict:
    """Load the VedaLang JSON schema."""
    with open(SCHEMA_DIR / "vedalang.schema.json") as f:
        return json.load(f)


def load_tableir_schema() -> dict:
    """Load the TableIR JSON schema."""
    with open(SCHEMA_DIR / "tableir.schema.json") as f:
        return json.load(f)


def validate_vedalang(source: dict) -> None:
    """Validate VedaLang source against schema."""
    schema = load_vedalang_schema()
    jsonschema.validate(source, schema)


def compile_vedalang_to_tableir(source: dict, validate: bool = True) -> dict:
    """
    Transform VedaLang source to TableIR structure.

    Args:
        source: VedaLang dictionary (parsed from .veda.yaml)
        validate: Whether to validate input/output against schemas

    Returns:
        TableIR dictionary ready for veda_emit_excel
    """
    if validate:
        validate_vedalang(source)

    model = source["model"]

    # Get regions from model
    regions = model.get("regions", ["REG1"])
    default_region = ",".join(regions)  # For multi-region models

    # Build commodity table (~FI_COMM)
    # Use lowercase column names for xl2times compatibility
    comm_rows = []
    for commodity in model.get("commodities", []):
        comm_rows.append({
            "region": default_region,
            "csets": _commodity_type_to_csets(commodity.get("type", "energy")),
            "commname": commodity["name"],
            "unit": commodity.get("unit", "PJ"),
        })

    # Build process table (~FI_PROCESS)
    # Use lowercase column names for xl2times compatibility
    process_rows = []
    for process in model.get("processes", []):
        process_rows.append({
            "region": default_region,
            "techname": process["name"],
            "techdesc": process.get("description", ""),
            "sets": ",".join(process.get("sets", [])),
            "tact": process.get("activity_unit", "PJ"),
            "tcap": process.get("capacity_unit", "GW"),
        })

    # Build topology table (~FI_T) for inputs/outputs
    # Use lowercase column names for xl2times compatibility
    topology_rows = []
    for process in model.get("processes", []):
        # Add input flows
        for inp in process.get("inputs", []):
            row = {
                "region": default_region,
                "techname": process["name"],
                "commodity-in": inp["commodity"],
            }
            if "share" in inp:
                row["share-i"] = inp["share"]
            topology_rows.append(row)

        # Add output flows
        for out in process.get("outputs", []):
            row = {
                "region": default_region,
                "techname": process["name"],
                "commodity-out": out["commodity"],
            }
            if "share" in out:
                row["share-o"] = out["share"]
            topology_rows.append(row)

        # Add efficiency if specified
        if "efficiency" in process:
            topology_rows.append({
                "region": default_region,
                "techname": process["name"],
                "eff": process["efficiency"],
            })

    # Build system settings tables
    regions = model.get("regions", ["REG1"])

    # ~BOOKREGIONS_MAP - maps book regions to internal regions
    bookregions_rows = [{"bookname": r, "region": r} for r in regions]

    # ~STARTYEAR - model start year
    start_year = model.get("start_year", 2020)
    startyear_rows = [{"value": start_year}]

    # ~ACTIVEPDEF - active period definition (required)
    # Set P for period-based time representation
    activepdef_rows = [{"value": "P"}]

    # ~TIMEPERIODS - define time periods (required)
    # The column name should match the active period definition (lowercased)
    # "p" means period lengths (years per period)
    # Default: 10 years per period (4 periods)
    time_periods = model.get("time_periods", [10, 10, 10, 10])
    timeperiods_rows = [{"p": period_length} for period_length in time_periods]

    # ~CURRENCIES - default currency
    currencies_rows = [{"currency": "USD"}]

    # Build scenario files (~TFM_INS-TS tables)
    scenario_files = []
    for scenario in model.get("scenarios", []):
        scenario_rows = _compile_scenario(scenario, default_region)
        if scenario_rows:
            scenario_file = {
                "path": f"Scen_{scenario['name']}/Scen_{scenario['name']}.xlsx",
                "sheets": [
                    {
                        "name": "Scenario",
                        "tables": [{"tag": "~TFM_INS-TS", "rows": scenario_rows}],
                    }
                ],
            }
            scenario_files.append(scenario_file)

    # Build TableIR structure
    tableir = {
        "files": [
            {
                "path": "SysSettings/SysSettings.xlsx",
                "sheets": [
                    {
                        "name": "SysSets",
                        "tables": [
                            {"tag": "~BOOKREGIONS_MAP", "rows": bookregions_rows},
                            {"tag": "~STARTYEAR", "rows": startyear_rows},
                            {"tag": "~ACTIVEPDEF", "rows": activepdef_rows},
                            {"tag": "~TIMEPERIODS", "rows": timeperiods_rows},
                            {"tag": "~CURRENCIES", "rows": currencies_rows},
                        ],
                    },
                    {
                        "name": "Commodities",
                        "tables": [{"tag": "~FI_COMM", "rows": comm_rows}],
                    },
                ],
            },
            {
                "path": "SubRES_TMPL/SubRES_Model.xlsx",
                "sheets": [
                    {
                        "name": "Processes",
                        "tables": [
                            {"tag": "~FI_PROCESS", "rows": process_rows},
                            {"tag": "~FI_T", "rows": topology_rows},
                        ],
                    }
                ],
            },
            *scenario_files,
        ]
    }

    if validate:
        tableir_schema = load_tableir_schema()
        jsonschema.validate(tableir, tableir_schema)

    return tableir


def _commodity_type_to_csets(ctype: str) -> str:
    """Map VedaLang commodity type to VEDA Csets."""
    mapping = {
        "energy": "NRG",
        "material": "MAT",
        "emission": "ENV",
        "demand": "DEM",
    }
    return mapping.get(ctype, "NRG")


def _compile_scenario(scenario: dict, region: str) -> list[dict]:
    """
    Compile a scenario definition to TableIR rows for ~TFM_INS-TS.

    Args:
        scenario: Scenario definition from VedaLang source
        region: Default region for the model

    Returns:
        List of rows for the ~TFM_INS-TS table
    """
    scenario_type = scenario.get("type")
    rows = []

    if scenario_type == "commodity_price":
        commodity = scenario["commodity"]
        values = scenario.get("values", {})
        for year, price in values.items():
            rows.append({
                "region": region,
                "year": int(year),
                "pset_co": commodity,
                "cost": price,
            })

    return rows


def load_vedalang(path: Path) -> dict:
    """Load VedaLang source from YAML file."""
    with open(path) as f:
        return yaml.safe_load(f)
