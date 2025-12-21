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

    # Derive model years for time-series expansion
    model_years = _get_model_years(model)

    # Build scenario files (~TFM_INS-TS tables)
    scenario_files = []
    for scenario in model.get("scenarios", []):
        scenario_rows = _compile_scenario(scenario, default_region, model_years)
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


def _get_model_years(model: dict) -> list[int]:
    """
    Derive the list of model representative years from start_year and time_periods.

    Args:
        model: The model dictionary from VedaLang source

    Returns:
        List of model years (e.g., [2020, 2030, 2040, 2050])
    """
    start_year = model.get("start_year", 2020)
    time_periods = model.get("time_periods", [10, 10, 10, 10])

    years = []
    y = start_year
    for p in time_periods:
        years.append(y)
        y += p
    return years


def _expand_series_to_years(
    sparse_values: dict[str, float],
    model_years: list[int],
    interpolation: str = "linear",
) -> dict[int, float]:
    """
    Expand sparse year->value mapping to dense values for all model years.

    No VEDA interpolation markers are used - all values are explicit.

    Args:
        sparse_values: Dictionary of year (as string) -> value
        model_years: List of model representative years
        interpolation: One of 'linear', 'step', 'hold'

    Returns:
        Dictionary of year (as int) -> interpolated value
    """
    # Convert string keys to int and sort
    points = sorted([(int(y), v) for y, v in sparse_values.items()])

    if not points:
        return {}

    result = {}

    for ym in model_years:
        # Check if exact match exists
        exact = next((v for y, v in points if y == ym), None)
        if exact is not None:
            result[ym] = exact
            continue

        # Find surrounding points
        before = [(y, v) for y, v in points if y < ym]
        after = [(y, v) for y, v in points if y > ym]

        if not before and not after:
            # No data at all
            continue
        elif not before:
            # Before first point
            if interpolation == "hold":
                result[ym] = after[0][1]
            # For linear/step, don't extrapolate before first point
        elif not after:
            # After last point
            if interpolation in ("hold", "step"):
                result[ym] = before[-1][1]
            # For linear, don't extrapolate after last point
        else:
            # Between two points
            y0, v0 = before[-1]
            y1, v1 = after[0]

            if interpolation == "linear":
                # Linear interpolation
                ratio = (ym - y0) / (y1 - y0)
                result[ym] = v0 + (v1 - v0) * ratio
            elif interpolation == "step":
                # Step: hold previous value
                result[ym] = v0
            elif interpolation == "hold":
                # Hold: also use previous value between points
                result[ym] = v0

    return result


def _compile_scenario(
    scenario: dict,
    region: str,
    model_years: list[int],
) -> list[dict]:
    """
    Compile a scenario definition to TableIR rows for ~TFM_INS-TS.

    Expands sparse time-series to dense rows for all model years.
    No VEDA interpolation markers are emitted.

    Args:
        scenario: Scenario definition from VedaLang source
        region: Default region for the model
        model_years: List of model representative years

    Returns:
        List of rows for the ~TFM_INS-TS table (one per model year)
    """
    scenario_type = scenario.get("type")
    rows = []

    if scenario_type == "commodity_price":
        commodity = scenario["commodity"]
        sparse_values = scenario.get("values", {})
        interpolation = scenario.get("interpolation", "linear")

        # Expand to all model years
        dense_values = _expand_series_to_years(
            sparse_values, model_years, interpolation
        )

        # Emit one row per year (canonical long format)
        for year in sorted(dense_values.keys()):
            rows.append({
                "region": region,
                "year": year,
                "pset_co": commodity,
                "cost": dense_values[year],
            })

    return rows


def load_vedalang(path: Path) -> dict:
    """Load VedaLang source from YAML file."""
    with open(path) as f:
        return yaml.safe_load(f)
