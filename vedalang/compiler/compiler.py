"""VedaLang to TableIR compiler."""

import json
from difflib import get_close_matches
from pathlib import Path

import jsonschema
import yaml

SCHEMA_DIR = Path(__file__).parent.parent / "schema"

# Unit categories for semantic validation
ENERGY_UNITS = {"PJ", "TJ", "GJ", "MWh", "GWh", "TWh", "MTOE", "KTOE"}
POWER_UNITS = {"GW", "MW", "kW", "TW"}
MASS_UNITS = {"Mt", "kt", "t", "Gt"}

# Default units by commodity type
DEFAULT_UNITS = {
    "energy": "PJ",
    "demand": "PJ",
    "emission": "Mt",
    "material": "Mt",
}

# Process attributes that support time-varying values
TIME_VARYING_ATTRS = {
    "efficiency", "invcost", "fixom", "varom", "life", "cost", "availability_factor"
}

# Map VedaLang attribute names to their TableIR/VEDA column names
# These must map to CANONICAL VEDA attribute column headers only
# (from attribute-master.json "column_header" field, NOT aliases)
ATTR_TO_COLUMN = {
    "efficiency": "eff",  # EFF canonical
    "invcost": "ncap_cost",  # NCAP_COST canonical (alias: invcost)
    "fixom": "ncap_fom",  # NCAP_FOM canonical (alias: fixom)
    "varom": "act_cost",  # ACT_COST canonical (alias: varom)
    "life": "ncap_tlife",  # NCAP_TLIFE canonical (alias: life)
    "cost": "ire_price",  # IRE_PRICE canonical (alias: cost)
    "availability_factor": "ncap_af",  # NCAP_AF canonical (aliases: cf, utilization)
}

# Interpolation mode to VEDA code mapping
INTERPOLATION_CODES = {
    "none": -1,
    "interp_only": 1,
    "interp_extrap_eps": 2,
    "interp_extrap": 3,
    "interp_extrap_back": 4,
    "interp_extrap_forward": 5,
}


def _is_time_varying(value) -> bool:
    """Check if a value is a time-varying specification (dict with 'values' key)."""
    return isinstance(value, dict) and "values" in value


def _normalize_process_flows(process: dict) -> dict:
    """
    Normalize process input/output shorthand to standard array format.

    Converts:
      input: "NG" → inputs: [{commodity: "NG"}]
      output: "ELC" → outputs: [{commodity: "ELC"}]

    Args:
        process: Process definition (may have shorthand or standard format)

    Returns:
        Process with normalized inputs/outputs arrays
    """
    result = process.copy()

    # Normalize single input string to array
    if "input" in result and "inputs" not in result:
        result["inputs"] = [{"commodity": result["input"]}]
        del result["input"]

    # Normalize single output string to array
    if "output" in result and "outputs" not in result:
        result["outputs"] = [{"commodity": result["output"]}]
        del result["output"]

    return result


def _get_default_unit(commodity_type: str) -> str:
    """Get default unit for a commodity type."""
    return DEFAULT_UNITS.get(commodity_type, "PJ")


def _get_scalar_value(value):
    """Get scalar value from scalar or time-varying spec (returns None for latter)."""
    if _is_time_varying(value):
        # Return None - caller should use _expand_time_varying_rows instead
        return None
    return value


def _expand_time_varying_attr(
    attr_name: str,
    value,
    base_row: dict,
) -> list[dict]:
    """
    Expand a time-varying attribute into multiple rows with YEAR column.

    Args:
        attr_name: The attribute name (e.g., 'invcost', 'efficiency')
        value: Either a scalar or a time-varying spec with 'values' dict
        base_row: Base row dict to copy for each year (region, techname, etc.)

    Returns:
        List of row dicts, one per year (or single row for scalar values)
    """
    column = ATTR_TO_COLUMN.get(attr_name, attr_name)

    if not _is_time_varying(value):
        # Scalar value - return single row
        row = base_row.copy()
        row[column] = value
        return [row]

    # Time-varying value - expand to multiple rows
    rows = []
    values = value["values"]
    interpolation = value.get("interpolation", "interp_extrap")
    interp_code = INTERPOLATION_CODES.get(interpolation, 3)

    # First, emit a year=0 row with interpolation code if not 'none'
    if interp_code != -1:
        interp_row = base_row.copy()
        interp_row["year"] = 0
        interp_row[column] = interp_code
        rows.append(interp_row)

    # Emit one row per year
    for year_str, val in sorted(values.items()):
        row = base_row.copy()
        row["year"] = int(year_str)
        row[column] = val
        rows.append(row)

    return rows


class SemanticValidationError(Exception):
    """Raised when semantic validation fails."""

    def __init__(self, errors: list[str], warnings: list[str] | None = None):
        self.errors = errors
        self.warnings = warnings or []
        super().__init__(self._format_message())

    def _format_message(self) -> str:
        parts = []
        if self.errors:
            parts.append(f"{len(self.errors)} semantic error(s):")
            for e in self.errors:
                parts.append(f"  - {e}")
        if self.warnings:
            parts.append(f"{len(self.warnings)} warning(s):")
            for w in self.warnings:
                parts.append(f"  - {w}")
        return "\n".join(parts)


def validate_cross_references(model: dict) -> tuple[list[str], list[str]]:
    """
    Validate semantic cross-references in the model.

    Checks that all referenced commodities, processes, and regions exist,
    and that scenario types target appropriate commodity types.

    Args:
        model: The model dictionary from VedaLang source

    Returns:
        Tuple of (errors, warnings)
    """
    errors: list[str] = []
    warnings: list[str] = []

    # Build lookup sets
    commodities = {c["name"]: c for c in model.get("commodities", [])}
    commodity_names = set(commodities.keys())
    processes = {p["name"] for p in model.get("processes", [])}
    regions = set(model.get("regions", []))

    def suggest_commodity(name: str) -> str:
        matches = get_close_matches(name, commodity_names, n=1, cutoff=0.6)
        if matches:
            return f" Did you mean '{matches[0]}'?"
        return ""

    def suggest_process(name: str) -> str:
        matches = get_close_matches(name, processes, n=1, cutoff=0.6)
        if matches:
            return f" Did you mean '{matches[0]}'?"
        return ""

    def suggest_region(name: str) -> str:
        matches = get_close_matches(name, regions, n=1, cutoff=0.6)
        if matches:
            return f" Did you mean '{matches[0]}'?"
        return ""

    # Validate process references
    for raw_process in model.get("processes", []):
        # Normalize shorthand syntax before validation
        process = _normalize_process_flows(raw_process)
        proc_name = process["name"]

        # Check input commodity references
        for i, inp in enumerate(process.get("inputs", [])):
            comm = inp["commodity"]
            if comm not in commodity_names:
                hint = suggest_commodity(comm)
                errors.append(
                    f"Unknown commodity '{comm}' in process "
                    f"'{proc_name}' inputs[{i}].{hint}"
                )

        # Check output commodity references
        for i, out in enumerate(process.get("outputs", [])):
            comm = out["commodity"]
            if comm not in commodity_names:
                hint = suggest_commodity(comm)
                errors.append(
                    f"Unknown commodity '{comm}' in process "
                    f"'{proc_name}' outputs[{i}].{hint}"
                )

        # Check unit compatibility (warnings only)
        activity_unit = process.get("activity_unit")
        if activity_unit and activity_unit not in ENERGY_UNITS:
            warnings.append(
                f"Process '{proc_name}' has activity_unit '{activity_unit}' "
                f"which is not a recognized energy unit. "
                f"Expected one of: {', '.join(sorted(ENERGY_UNITS))}"
            )

        capacity_unit = process.get("capacity_unit")
        if capacity_unit and capacity_unit not in POWER_UNITS:
            warnings.append(
                f"Process '{proc_name}' has capacity_unit '{capacity_unit}' "
                f"which is not a recognized power unit. "
                f"Expected one of: {', '.join(sorted(POWER_UNITS))}"
            )

    # Validate constraint references
    for constraint in model.get("constraints", []):
        constraint_name = constraint["name"]

        # Check commodity reference
        commodity = constraint.get("commodity")
        if commodity and commodity not in commodity_names:
            hint = suggest_commodity(commodity)
            errors.append(
                f"Unknown commodity '{commodity}' in constraint "
                f"'{constraint_name}'.{hint}"
            )

        # Check process references (for activity_share constraints)
        for proc in constraint.get("processes", []):
            if proc not in processes:
                hint = suggest_process(proc)
                errors.append(
                    f"Unknown process '{proc}' in constraint '{constraint_name}'.{hint}"
                )

    # Validate trade link references
    for i, link in enumerate(model.get("trade_links", [])):
        origin = link["origin"]
        destination = link["destination"]
        commodity = link["commodity"]

        if origin not in regions:
            hint = suggest_region(origin)
            errors.append(
                f"Unknown region '{origin}' in trade_links[{i}] origin.{hint}"
            )

        if destination not in regions:
            hint = suggest_region(destination)
            errors.append(
                f"Unknown region '{destination}' in trade_links[{i}] destination.{hint}"
            )

        if commodity not in commodity_names:
            hint = suggest_commodity(commodity)
            errors.append(
                f"Unknown commodity '{commodity}' in trade_links[{i}].{hint}"
            )

    # Validate scenario references
    for scenario in model.get("scenarios", []):
        scenario_name = scenario["name"]
        scenario_type = scenario.get("type")
        commodity = scenario.get("commodity")

        if commodity:
            if commodity not in commodity_names:
                hint = suggest_commodity(commodity)
                errors.append(
                    f"Unknown commodity '{commodity}' in scenario "
                    f"'{scenario_name}'.{hint}"
                )
            else:
                # Check commodity type matches scenario type
                comm_info = commodities[commodity]
                comm_type = comm_info.get("type", "energy")

                if scenario_type == "demand_projection":
                    if comm_type != "demand":
                        errors.append(
                            f"demand_projection scenario '{scenario_name}' targets "
                            f"commodity '{commodity}' (type '{comm_type}'), "
                            "expected 'demand'"
                        )

                elif scenario_type == "commodity_price":
                    if comm_type == "demand":
                        errors.append(
                            f"commodity_price scenario '{scenario_name}' targets "
                            f"commodity '{commodity}' (type 'demand'), "
                            "expected non-demand type"
                        )

    return errors, warnings


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
        validate: Whether to validate input/output against schemas and semantics

    Returns:
        TableIR dictionary ready for veda_emit_excel

    Raises:
        jsonschema.ValidationError: If source doesn't match VedaLang schema
        SemanticValidationError: If cross-references are invalid
    """
    if validate:
        validate_vedalang(source)

    model = source["model"]

    # Semantic cross-reference validation (before any emission)
    if validate:
        errors, warnings = validate_cross_references(model)
        if errors:
            raise SemanticValidationError(errors, warnings)

    # Get regions from model
    regions = model.get("regions", ["REG1"])
    default_region = ",".join(regions)  # For multi-region models

    # Build commodity table (~FI_COMM)
    # Use lowercase column names for xl2times compatibility
    comm_rows = []
    for commodity in model.get("commodities", []):
        comm_type = commodity.get("type", "energy")
        # Use explicit unit or default based on commodity type
        unit = commodity.get("unit") or _get_default_unit(comm_type)
        comm_rows.append({
            "region": default_region,
            "csets": _commodity_type_to_csets(comm_type),
            "commodity": commodity["name"],
            "unit": unit,
        })

    # Build process table (~FI_PROCESS)
    # Use lowercase column names for xl2times compatibility
    # primary_commodity_group is REQUIRED in schema - use directly, no inference
    process_rows = []
    for raw_process in model.get("processes", []):
        # Normalize shorthand input/output syntax
        process = _normalize_process_flows(raw_process)
        process_rows.append({
            "region": default_region,
            "process": process["name"],
            "description": process.get("description", ""),
            "sets": ",".join(process.get("sets", [])),
            "tact": process.get("activity_unit", "PJ"),
            "tcap": process.get("capacity_unit", "GW"),
            "primarycg": process["primary_commodity_group"],
        })

    # Build topology table (~FI_T) for inputs/outputs
    # Use lowercase column names for xl2times compatibility
    topology_rows = []
    for raw_process in model.get("processes", []):
        # Normalize shorthand input/output syntax
        process = _normalize_process_flows(raw_process)
        inputs = process.get("inputs", [])
        outputs = process.get("outputs", [])

        # Collect cost parameters - separate scalar from time-varying
        # Keys in cost_params use CANONICAL column names from ATTR_TO_COLUMN
        cost_params = {}  # Scalar values to merge into rows (canonical column names)
        time_varying_attrs = []  # (attr_name, value) tuples for separate rows
        for attr in ["invcost", "fixom", "varom", "life", "cost"]:
            if attr in process:
                val = process[attr]
                # Map VedaLang attr name to canonical column name
                column = ATTR_TO_COLUMN.get(attr, attr)
                if _is_time_varying(val):
                    time_varying_attrs.append((attr, val))
                else:
                    cost_params[column] = val

        # Add input flows
        for inp in inputs:
            row = {
                "region": default_region,
                "process": process["name"],
                "commodity-in": inp["commodity"],
            }
            if "share" in inp:
                row["share-i"] = inp["share"]
            topology_rows.append(row)

        # Add output flows - merge cost params into first output row if no eff
        for i, out in enumerate(outputs):
            row = {
                "region": default_region,
                "process": process["name"],
                "commodity-out": out["commodity"],
            }
            if "share" in out:
                row["share-o"] = out["share"]
            # Merge cost params into first output row if no efficiency specified
            if i == 0 and "efficiency" not in process and cost_params:
                row.update(cost_params)
                cost_params = {}  # Clear so we don't add again
            topology_rows.append(row)

        # Collect bound parameters
        bound_params = _collect_bound_params(process)

        # Add efficiency row with cost and bound parameters if specified
        if "efficiency" in process:
            eff_val = process["efficiency"]
            if _is_time_varying(eff_val):
                # Time-varying efficiency - add to time_varying_attrs
                time_varying_attrs.append(("efficiency", eff_val))
                # Still emit a base row with scalar cost params if any
                if cost_params:
                    row = {
                        "region": default_region,
                        "process": process["name"],
                    }
                    row.update(cost_params)
                    if bound_params:
                        first_bound = bound_params.pop(0)
                        row.update(first_bound)
                    topology_rows.append(row)
            else:
                # Scalar efficiency
                row = {
                    "region": default_region,
                    "process": process["name"],
                    "eff": eff_val,
                }
                row.update(cost_params)
                # Merge first bound into efficiency row if present
                if bound_params:
                    first_bound = bound_params.pop(0)
                    row.update(first_bound)
                topology_rows.append(row)

        # Emit remaining bounds merged with commodity-out references
        # xl2times requires rows to have Comm-IN, Comm-OUT, EFF, or Value
        for bound_param in bound_params:
            # Find first output commodity for this process
            first_output = outputs[0]["commodity"] if outputs else None
            row = {
                "region": default_region,
                "process": process["name"],
            }
            if first_output:
                row["commodity-out"] = first_output
            row.update(bound_param)
            topology_rows.append(row)

        # Emit time-varying attributes as separate year-indexed rows
        # xl2times requires at least one commodity reference per row
        first_output = outputs[0]["commodity"] if outputs else None
        for attr_name, attr_value in time_varying_attrs:
            base_row = {
                "region": default_region,
                "process": process["name"],
            }
            if first_output:
                base_row["commodity-out"] = first_output
            expanded_rows = _expand_time_varying_attr(attr_name, attr_value, base_row)
            topology_rows.extend(expanded_rows)

    # Build system settings tables
    regions = model.get("regions", ["REG1"])

    # ~BOOKREGIONS_MAP - maps book regions to internal regions
    # Use a single bookname for all regions to ensure all are treated as internal
    # The bookname must match the VT_{bookname}_* file pattern
    # IMPORTANT: Bookname must be uppercase for xl2times compatibility
    model_name = model.get("name", "Model")
    bookname = model_name.upper()  # Uppercase for xl2times BookRegions_Map matching
    bookregions_rows = [{"bookname": bookname, "region": r} for r in regions]

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

    # Build scenario files (~TFM_DINS-AT tables) for commodity_price scenarios
    # Uses ~TFM_DINS-AT instead of ~TFM_INS for VedaOnline compatibility
    scenario_files = []
    for scenario in model.get("scenarios", []):
        scenario_rows = _compile_scenario(scenario, default_region, model_years)
        if scenario_rows:
            scenario_file = {
                "path": f"SuppXLS/Scen_{scenario['name']}.xlsx",
                "sheets": [
                    {
                        "name": "Scenario",
                        "tables": [{"tag": "~TFM_DINS-AT", "rows": scenario_rows}],
                    }
                ],
            }
            scenario_files.append(scenario_file)

    # Compile demand projections - these go into ~FI_T table
    demand_projection_rows = _compile_demand_projections(
        model.get("scenarios", []), default_region, model_years
    )
    topology_rows.extend(demand_projection_rows)

    # Compile timeslices if defined
    timeslice_rows = []
    yrfr_rows = []
    if "timeslices" in model:
        timeslice_rows, yrfr_rows = _compile_timeslices(
            model["timeslices"], regions
        )

    # Build SysSets tables list
    syssets_tables = [
        {"tag": "~BOOKREGIONS_MAP", "rows": bookregions_rows},
        {"tag": "~STARTYEAR", "rows": startyear_rows},
        {"tag": "~ACTIVEPDEF", "rows": activepdef_rows},
        {"tag": "~TIMEPERIODS", "rows": timeperiods_rows},
        {"tag": "~CURRENCIES", "rows": currencies_rows},
    ]

    # Add timeslice table if defined
    if timeslice_rows:
        syssets_tables.append({"tag": "~TIMESLICES", "rows": timeslice_rows})

    # Build SysSettings sheets list
    syssettings_sheets = [
        {"name": "SysSets", "tables": syssets_tables},
        {"name": "Commodities", "tables": [{"tag": "~FI_COMM", "rows": comm_rows}]},
    ]

    # Add constants sheet with YRFR if timeslices defined
    if yrfr_rows:
        syssettings_sheets.append({
            "name": "constants",
            "tables": [{"tag": "~TFM_INS", "rows": yrfr_rows}],
        })

    # Build process file - use VT_{bookname}_ prefix for internal region recognition
    # All regions map to this single bookname via BOOKREGIONS_MAP
    process_file_path = f"VT_{bookname}_{model_name}.xlsx"

    # Compile trade links if present - returns files, process declarations, and topology
    trade_link_files, trade_process_rows, trade_topology_rows = _compile_trade_links(
        model.get("trade_links", []),
        model.get("commodities", []),
    )

    # Merge trade process declarations into main process/topology rows
    process_rows.extend(trade_process_rows)
    topology_rows.extend(trade_topology_rows)

    # Compile constraints if present - returns UC file(s)
    constraint_files = _compile_constraints(
        model.get("constraints", []),
        default_region,
        model_years,
    )

    # Build TableIR structure
    tableir = {
        "files": [
            {
                "path": "SysSettings.xlsx",
                "sheets": syssettings_sheets,
            },
            {
                "path": process_file_path,
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
            *trade_link_files,
            *constraint_files,
        ]
    }

    if validate:
        tableir_schema = load_tableir_schema()
        jsonschema.validate(tableir, tableir_schema)

        # Validate against VEDA table schemas (canonical column names only)
        from .table_schemas import TableValidationError, validate_tableir

        table_errors = validate_tableir(tableir)
        if table_errors:
            raise TableValidationError(table_errors)

    return tableir


def _collect_bound_params(process: dict) -> list[dict]:
    """
    Collect bound parameters from process definition.

    Each bound type (activity_bound, cap_bound, ncap_bound) can have up to three
    limits (up, lo, fx), each returned as a separate dict with limtype and column.

    These params are designed to be merged into ~FI_T rows that have other
    required fields (commodity-out, eff, etc.).

    Args:
        process: Process definition from VedaLang source

    Returns:
        List of dicts with {limtype, <bound_column>: value}
    """
    params = []

    # Mapping: VedaLang field -> VEDA column name
    bound_mapping = {
        "activity_bound": "act_bnd",
        "cap_bound": "cap_bnd",
        "ncap_bound": "ncap_bnd",
    }

    # Mapping: VedaLang limtype key -> VEDA limtype value
    limtype_mapping = {
        "up": "UP",
        "lo": "LO",
        "fx": "FX",
    }

    for vedalang_field, veda_column in bound_mapping.items():
        bound_spec = process.get(vedalang_field)
        if not bound_spec:
            continue

        for limit_key, limit_value in bound_spec.items():
            if limit_key not in limtype_mapping:
                continue
            params.append({
                "limtype": limtype_mapping[limit_key],
                veda_column: limit_value,
            })

    return params


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
    interpolation: str,
) -> dict[int, float]:
    """
    Expand sparse year->value mapping to dense values for all model years.

    Uses VEDA-compatible interpolation/extrapolation semantics but performs
    the expansion at compile time (no year=0 rows emitted).

    Args:
        sparse_values: Dictionary of year (as string) -> value
        model_years: List of model representative years
        interpolation: One of the VEDA-compatible modes:
            - none: No interpolation/extrapolation (only specified years)
            - interp_only: Interpolate between points, no extrapolation
            - interp_extrap_eps: Interpolate, extrapolate with EPS (tiny value)
            - interp_extrap: Full interpolation and extrapolation
            - interp_extrap_back: Interpolate, backward extrapolation only
            - interp_extrap_forward: Interpolate, forward extrapolation only

    Returns:
        Dictionary of year (as int) -> interpolated value
    """
    # Convert string keys to int and sort
    points = sorted([(int(y), v) for y, v in sparse_values.items()])

    if not points:
        return {}

    result = {}
    first_year, first_val = points[0]
    last_year, last_val = points[-1]

    # Determine extrapolation behavior based on mode
    extrap_backward = interpolation in ("interp_extrap", "interp_extrap_back")
    extrap_forward = interpolation in (
        "interp_extrap", "interp_extrap_forward", "interp_extrap_eps"
    )
    do_interpolate = interpolation != "none"

    for ym in model_years:
        # Check if exact match exists
        exact = next((v for y, v in points if y == ym), None)
        if exact is not None:
            result[ym] = exact
            continue

        # If no interpolation, skip non-specified years
        if not do_interpolate:
            continue

        # Find surrounding points
        before = [(y, v) for y, v in points if y < ym]
        after = [(y, v) for y, v in points if y > ym]

        if not before:
            # Before first point - backward extrapolation
            if extrap_backward:
                result[ym] = first_val
            # else: skip this year
        elif not after:
            # After last point - forward extrapolation
            if extrap_forward:
                result[ym] = last_val
            # else: skip this year
        else:
            # Between two points - linear interpolation
            y0, v0 = before[-1]
            y1, v1 = after[0]
            ratio = (ym - y0) / (y1 - y0)
            result[ym] = v0 + (v1 - v0) * ratio

    return result


def _compile_scenario(
    scenario: dict,
    region: str,
    model_years: list[int],
) -> list[dict]:
    """
    Compile a scenario definition to TableIR rows for ~TFM_DINS-AT.

    Uses ~TFM_DINS-AT tag (not ~TFM_INS) for VedaOnline compatibility.
    The attribute name becomes a column header, not a 'value' column.

    Expands sparse time-series to dense rows for all model years using
    VEDA-compatible interpolation semantics. No year=0 rows are emitted;
    the compiler handles all interpolation.

    Args:
        scenario: Scenario definition from VedaLang source
        region: Default region for the model
        model_years: List of model representative years

    Returns:
        List of rows for the ~TFM_DINS-AT table (one row per specified year)
    """
    scenario_type = scenario.get("type")
    rows = []

    if scenario_type == "commodity_price":
        commodity = scenario["commodity"]
        sparse_values = scenario.get("values", {})

        # Use TFM_DINS-AT with attribute as column header (not 'value' column)
        # cset_cn = explicit commodity name
        # com_cstnet = cost on net of commodity (lowercase for xl2times)
        for year_str, value in sorted(sparse_values.items()):
            rows.append({
                "region": region,
                "cset_cn": commodity,
                "year": int(year_str),
                "com_cstnet": value,
            })

    # Note: demand_projection is handled separately in compile_vedalang_to_tableir
    # as it emits to ~FI_T table, not ~TFM_DINS-AT

    return rows


def _compile_demand_projections(
    scenarios: list[dict],
    region: str,
    model_years: list[int],
) -> list[dict]:
    """
    Compile demand_projection scenarios to TableIR rows for ~FI_T.

    Uses wide-in-attribute format where 'DEMAND' is a column header
    (not a value in an 'attribute' column). This is the correct FI-style
    format where attributes are column headers with no 'value' column.

    Args:
        scenarios: List of scenario definitions from VedaLang source
        region: Default region for the model
        model_years: List of model representative years

    Returns:
        List of rows for the ~FI_T table (one per model year per commodity)
    """
    rows = []

    for scenario in scenarios:
        if scenario.get("type") != "demand_projection":
            continue

        commodity = scenario["commodity"]
        sparse_values = scenario.get("values", {})
        interpolation = scenario["interpolation"]

        # Expand to all model years using VEDA-compatible interpolation
        dense_values = _expand_series_to_years(
            sparse_values, model_years, interpolation
        )

        # Wide-in-attribute format: com_proj is a column header, not a value
        # This matches VEDA FI-style tables where attributes are columns
        # NOTE: Use canonical 'com_proj', not alias 'demand'
        for year in sorted(dense_values.keys()):
            rows.append({
                "region": region,
                "commodity": commodity,
                "year": year,
                "com_proj": dense_values[year],  # Canonical attribute name
            })

    return rows


def _compile_trade_links(
    trade_links: list[dict],
    commodities: list[dict],
) -> tuple[list[dict], list[dict], list[dict]]:
    """
    Compile trade link definitions to TableIR structures.

    Uses the matrix format ~TRADELINKS because xl2times harmonise_tradelinks
    properly converts it.

    IMPORTANT: VedaLang explicitly emits trade process declarations to ~FI_PROCESS
    to avoid relying on xl2times's complete_processes auto-generation.

    VedaOnline compatibility: ~FI_T tables are NOT allowed in ScenTrade files.
    Trade efficiency rows are returned as topology_rows to be emitted in the
    base VT_* file (which does allow ~FI_T).

    Matrix format: sheet name encodes direction (Bi_COMM or Uni_COMM),
    first column is commodity, other columns are destination regions.
    Cell value is explicit process name (NOT numeric 1).

    Process naming follows VEDA convention: T{B|U}_{COMM}_{REG1}_{REG2}_01

    Args:
        trade_links: List of trade link definitions from VedaLang source
        commodities: List of commodity definitions (for unit lookup)

    Returns:
        Tuple of:
        - List of TableIR file definitions (ScenTrade file with ~TRADELINKS only)
        - List of process declaration rows for ~FI_PROCESS
        - List of topology rows for ~FI_T (includes trade efficiency rows)
    """
    if not trade_links:
        return [], [], []

    from collections import defaultdict

    # Build commodity lookup for unit
    comm_units = {c["name"]: c.get("unit", "PJ") for c in commodities}

    # Group trade links by commodity and bidirectional flag
    grouped: dict[tuple[str, bool], list[dict]] = defaultdict(list)
    for link in trade_links:
        commodity = link["commodity"]
        bidirectional = link.get("bidirectional", True)
        grouped[(commodity, bidirectional)].append(link)

    # Build sheets for trade links (matrix format)
    tradelink_sheets = []
    process_rows = []  # Explicit trade process declarations
    topology_rows = []  # Trade process topology (inputs/outputs) + efficiency
    emitted_processes: set[str] = set()  # Track to avoid duplicates

    for (commodity, bidirectional), links in grouped.items():
        # Sheet name encodes direction and commodity
        direction = "Bi" if bidirectional else "Uni"
        sheet_name = f"{direction}_{commodity}"
        direction_code = "B" if bidirectional else "U"

        # Collect all unique regions for matrix
        all_regions: set[str] = set()
        for link in links:
            all_regions.add(link["origin"])
            all_regions.add(link["destination"])

        # Build matrix rows - one row per origin, columns are destinations
        rows = []
        for origin in sorted(all_regions):
            # Check if this origin has any outgoing links
            outgoing = [lnk for lnk in links if lnk["origin"] == origin]
            if not outgoing:
                continue

            row: dict = {commodity: origin}
            for link in outgoing:
                dest = link["destination"]
                efficiency = link.get("efficiency")

                # Generate predictable process name
                process_name = f"T_{direction_code}_{commodity}_{origin}_{dest}_01"

                # Cell value: use explicit process name
                row[dest] = process_name

                # Emit explicit process declaration for ORIGIN region
                # (IRE processes are declared in the exporting region)
                if process_name not in emitted_processes:
                    unit = comm_units.get(commodity, "PJ")
                    process_rows.append({
                        "region": origin,
                        "process": process_name,
                        "description": f"Trade {commodity} from {origin} to {dest}",
                        "sets": "IRE",
                        "tact": unit,
                        "tcap": "",  # Trade processes typically don't have capacity
                    })

                    # For bidirectional, also declare in destination region
                    if bidirectional:
                        process_rows.append({
                            "region": dest,
                            "process": process_name,
                            "description": f"Trade {commodity} from {origin} to {dest}",
                            "sets": "IRE",
                            "tact": unit,
                            "tcap": "",
                        })

                    # Emit topology rows - IRE processes need commodity flows
                    # Origin exports (OUT), destination imports (IN)
                    topology_rows.append({
                        "region": origin,
                        "process": process_name,
                        "commodity-out": commodity,
                    })
                    topology_rows.append({
                        "region": dest,
                        "process": process_name,
                        "commodity-in": commodity,
                    })

                    emitted_processes.add(process_name)

                # If efficiency specified, add to topology_rows (goes to base VT_* file)
                # VedaOnline does NOT allow ~FI_T in ScenTrade files
                if efficiency is not None:
                    topology_rows.append({
                        "region": origin,
                        "process": process_name,
                        "commodity-out": commodity,
                        "eff": efficiency,
                    })

            rows.append(row)

        tradelink_sheets.append({
            "name": sheet_name,
            "tables": [{"tag": "~TRADELINKS", "rows": rows}],
        })

    # Build trade file with ~TRADELINKS only (no ~FI_T for VedaOnline compatibility)
    trade_file = {
        "path": "SuppXLS/Trades/ScenTrade__Trade_Links.xlsx",
        "sheets": tradelink_sheets,
    }

    return [trade_file], process_rows, topology_rows


def _compile_timeslices(
    timeslices: dict,
    regions: list[str],
) -> tuple[list[dict], list[dict]]:
    """
    Compile timeslice definitions to TableIR tables.

    Generates:
    1. ~TIMESLICES table with season/weekly/daynite columns
    2. ~TFM_INS rows with attribute=YRFR for year fractions

    The ~TIMESLICES table format emits parent codes and explicit leaf timeslice
    names. This gives VedaLang explicit control over timeslice naming rather
    than relying on xl2times cross-product expansion.

    For example, with seasons [S, W] and daynites [D, N], we emit:
        Season | Weekly | DayNite
        S      |        |         <- parent season code
        W      |        |         <- parent season code
               |        | SD      <- explicit leaf timeslice
               |        | SN
               |        | WD
               |        | WN

    Args:
        timeslices: Timeslice definition from VedaLang source
        regions: List of region codes

    Returns:
        Tuple of (timeslice_rows, yrfr_rows)
    """
    season_codes = [s["code"] for s in timeslices.get("season", [])]
    weekly_codes = [w["code"] for w in timeslices.get("weekly", [])]
    daynite_codes = [d["code"] for d in timeslices.get("daynite", [])]

    timeslice_rows = []

    # Emit parent season codes (each on its own row with empty other columns)
    for season in season_codes:
        timeslice_rows.append({
            "season": season,
            "weekly": "",
            "daynite": "",
        })

    # Emit parent weekly codes (if any)
    for weekly in weekly_codes:
        timeslice_rows.append({
            "season": "",
            "weekly": weekly,
            "daynite": "",
        })

    # Generate and emit explicit leaf timeslice names
    # The leaf names are the concatenation of all level codes
    leaf_timeslices = _generate_leaf_timeslices(
        season_codes, weekly_codes, daynite_codes
    )
    for leaf in leaf_timeslices:
        timeslice_rows.append({
            "season": "",
            "weekly": "",
            "daynite": leaf,
        })

    # Build ~TFM_INS rows for year fractions
    fractions = timeslices.get("fractions", {})
    yrfr_rows = []
    for ts_name, fraction in fractions.items():
        # YRFR applies to all regions via allregions column
        yrfr_rows.append({
            "timeslice": ts_name,
            "attribute": "YRFR",
            "allregions": fraction,
        })

    return timeslice_rows, yrfr_rows


def _generate_leaf_timeslices(
    seasons: list[str],
    weeklies: list[str],
    daynites: list[str],
) -> list[str]:
    """
    Generate explicit leaf timeslice names by concatenating level codes.

    The leaf timeslice name is formed by concatenating codes from each level
    in order: season + weekly + daynite.

    Args:
        seasons: List of season codes (e.g., ["S", "W"])
        weeklies: List of weekly codes (e.g., [])
        daynites: List of daynite codes (e.g., ["D", "N"])

    Returns:
        List of leaf timeslice names (e.g., ["SD", "SN", "WD", "WN"])
    """
    import itertools

    # Use [""] as placeholder for empty levels to ensure product works
    s_list = seasons if seasons else [""]
    w_list = weeklies if weeklies else [""]
    d_list = daynites if daynites else [""]

    leaves = []
    for s, w, d in itertools.product(s_list, w_list, d_list):
        leaf = s + w + d
        if leaf:  # Only add non-empty leaf names
            leaves.append(leaf)

    return leaves


def _compile_constraints(
    constraints: list[dict],
    region: str,
    model_years: list[int],
) -> list[dict]:
    """
    Compile constraint definitions to TableIR files with ~UC_T tables.

    Supports two constraint types:
    1. emission_cap: Bounds on commodity production (uses UC_COMPRD + UC_RHSRT)
    2. activity_share: Share constraints on process activity (uses UC_ACT + UC_RHSRT)

    Args:
        constraints: List of constraint definitions from VedaLang source
        region: Default region for the model
        model_years: List of model representative years

    Returns:
        List of TableIR file definitions containing ~UC_T tables
    """
    if not constraints:
        return []

    uc_rows = []

    for constraint in constraints:
        constraint_type = constraint["type"]
        uc_name = constraint["name"]
        commodity = constraint.get("commodity")
        limtype = constraint.get("limtype", "up").upper()

        if constraint_type == "emission_cap":
            uc_rows.extend(
                _compile_emission_cap(
                    uc_name, commodity, constraint, region, model_years, limtype
                )
            )
        elif constraint_type == "activity_share":
            uc_rows.extend(
                _compile_activity_share(
                    uc_name, commodity, constraint, region, model_years
                )
            )

    if not uc_rows:
        return []

    # Build UC file with uc_sets metadata
    # Default UC scope: R_E (each region), T_E (each period)
    # This tells xl2times how to expand the constraints
    return [
        {
            "path": "SuppXLS/Scen_UC_Constraints.xlsx",
            "sheets": [
                {
                    "name": "UC_Constraints",
                    "tables": [
                        {
                            "tag": "~UC_T",
                            "uc_sets": {
                                "R_E": "AllRegions",
                                "T_E": "",
                            },
                            "rows": uc_rows,
                        }
                    ],
                }
            ],
        }
    ]


def _compile_emission_cap(
    uc_name: str,
    commodity: str,
    constraint: dict,
    region: str,
    model_years: list[int],
    limtype: str,
) -> list[dict]:
    """
    Compile an emission_cap constraint to ~UC_T rows.

    VedaOnline compatibility: uses attribute name as column header (not 'value').
    UC_N is the row identifier, UC_RHS is the column header for RHS values.

    Emission cap uses:
    - UC_COMPRD with coefficient 1 (LHS side) to sum commodity production
    - UC_RHS with the limit value (RHS side)

    Args:
        uc_name: Constraint name
        commodity: Target commodity to cap
        constraint: Full constraint definition
        region: Model region
        model_years: List of model years
        limtype: Limit type (UP, LO, FX)

    Returns:
        List of ~UC_T rows
    """
    rows = []

    # Get RHS values - either single limit or year-specific
    if "years" in constraint:
        sparse_values = constraint["years"]
        interpolation = constraint.get("interpolation", "interp_extrap")
        dense_values = _expand_series_to_years(
            sparse_values, model_years, interpolation
        )
    elif "limit" in constraint:
        # Single limit applies to all years
        dense_values = {y: constraint["limit"] for y in model_years}
    else:
        # No limit specified - skip this constraint
        return []

    # Emit LHS coefficient row: UC_COMPRD for the commodity
    # Use uc_comprd as column header (lowercase for xl2times)
    description = f"Emission cap on {commodity}"
    for year in sorted(dense_values.keys()):
        rows.append({
            "uc_n": uc_name,
            "description": description,
            "region": region,
            "year": year,
            "commodity": commodity,
            "side": "LHS",
            "uc_comprd": 1,
        })

    # Use uc_rhsrt (region + year variant) for year-specific RHS values
    # UC_RHSRT indexes: [region, uc_n, year, limtype]
    for year in sorted(dense_values.keys()):
        rows.append({
            "uc_n": uc_name,
            "description": description,
            "region": region,
            "year": year,
            "limtype": limtype,
            "uc_rhsrt": dense_values[year],
        })

    return rows


def _compile_activity_share(
    uc_name: str,
    commodity: str,
    constraint: dict,
    region: str,
    model_years: list[int],
) -> list[dict]:
    """
    Compile an activity_share constraint to ~UC_T rows.

    Activity share uses:
    - UC_ACT with coefficient 1 for target processes (LHS)
    - UC_ACT with -share for all processes producing the commodity (LHS)
    - UC_RHSRT with 0 (constraint is: target >= share * total)

    For minimum_share: limtype=LO; for maximum_share: limtype=UP.

    Simplified approach: use commodity production as the denominator.

    Args:
        uc_name: Constraint name
        commodity: Reference commodity (e.g., ELC)
        constraint: Full constraint definition
        region: Model region
        model_years: List of model years

    Returns:
        List of ~UC_T rows
    """
    rows = []
    processes = constraint.get("processes", [])
    minimum_share = constraint.get("minimum_share")
    maximum_share = constraint.get("maximum_share")

    if not processes:
        return []

    # Generate rows for minimum share constraint
    if minimum_share is not None:
        rows.extend(
            _compile_share_constraint(
                uc_name + "_LO" if maximum_share is not None else uc_name,
                commodity,
                processes,
                minimum_share,
                "LO",
                region,
                model_years,
            )
        )

    # Generate rows for maximum share constraint
    if maximum_share is not None:
        rows.extend(
            _compile_share_constraint(
                uc_name + "_UP" if minimum_share is not None else uc_name,
                commodity,
                processes,
                maximum_share,
                "UP",
                region,
                model_years,
            )
        )

    return rows


def _compile_share_constraint(
    uc_name: str,
    commodity: str,
    processes: list[str],
    share: float,
    limtype: str,
    region: str,
    model_years: list[int],
) -> list[dict]:
    """
    Compile a single share constraint (either min or max).

    VedaOnline compatibility: uses attribute name as column header (not 'value').
    UC_ACT, UC_COMPRD, UC_RHS become column headers.

    The constraint is: sum(process_act) - share * commodity_prod {>= | <=} 0.

    Args:
        uc_name: Constraint name
        commodity: Reference commodity
        processes: Target processes
        share: Share value (0-1)
        limtype: LO for minimum, UP for maximum
        region: Model region
        model_years: List of model years

    Returns:
        List of ~UC_T rows
    """
    rows = []
    bound_type = "minimum" if limtype == "LO" else "maximum"
    description = f"Activity share ({bound_type} {share:.0%}) on {commodity}"

    for year in model_years:
        # LHS: Add target process activities with coefficient 1
        # Use uc_act as column header (lowercase for xl2times)
        for process in processes:
            rows.append({
                "uc_n": uc_name,
                "description": description,
                "region": region,
                "year": year,
                "process": process,
                "side": "LHS",
                "uc_act": 1,
            })

        # LHS: Subtract share * commodity production
        # Use uc_comprd as column header (lowercase for xl2times)
        rows.append({
            "uc_n": uc_name,
            "description": description,
            "region": region,
            "year": year,
            "commodity": commodity,
            "side": "LHS",
            "uc_comprd": -share,
        })

        # RHS: The bound is 0
        # Use uc_rhsrt (region + year variant) since we have year-specific constraints
        rows.append({
            "uc_n": uc_name,
            "description": description,
            "region": region,
            "year": year,
            "limtype": limtype,
            "uc_rhsrt": 0,
        })

    return rows


def load_vedalang(path: Path) -> dict:
    """Load VedaLang source from YAML file."""
    with open(path) as f:
        return yaml.safe_load(f)
