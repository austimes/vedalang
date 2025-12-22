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
    commodities_by_name: dict[str, dict] = {}
    for commodity in model.get("commodities", []):
        commodities_by_name[commodity["name"]] = commodity
        comm_rows.append({
            "region": default_region,
            "csets": _commodity_type_to_csets(commodity.get("type", "energy")),
            "commname": commodity["name"],
            "unit": commodity.get("unit", "PJ"),
        })

    # Build process table (~FI_PROCESS)
    # Use lowercase column names for xl2times compatibility
    # Always emit primarycg - either explicit or inferred
    process_rows = []
    for process in model.get("processes", []):
        pcg = process.get("primary_commodity_group") or _infer_primary_commodity_group(
            process, commodities_by_name
        )
        process_rows.append({
            "region": default_region,
            "techname": process["name"],
            "techdesc": process.get("description", ""),
            "sets": ",".join(process.get("sets", [])),
            "tact": process.get("activity_unit", "PJ"),
            "tcap": process.get("capacity_unit", "GW"),
            "primarycg": pcg,
        })

    # Build topology table (~FI_T) for inputs/outputs
    # Use lowercase column names for xl2times compatibility
    topology_rows = []
    for process in model.get("processes", []):
        inputs = process.get("inputs", [])
        outputs = process.get("outputs", [])

        # Collect cost parameters to merge into rows
        cost_params = {}
        if "invcost" in process:
            cost_params["invcost"] = process["invcost"]
        if "fixom" in process:
            cost_params["fixom"] = process["fixom"]
        if "varom" in process:
            cost_params["varom"] = process["varom"]
        if "life" in process:
            cost_params["life"] = process["life"]
        if "cost" in process:
            cost_params["cost"] = process["cost"]

        # Add input flows
        for inp in inputs:
            row = {
                "region": default_region,
                "techname": process["name"],
                "commodity-in": inp["commodity"],
            }
            if "share" in inp:
                row["share-i"] = inp["share"]
            topology_rows.append(row)

        # Add output flows - merge cost params into first output row if no eff
        for i, out in enumerate(outputs):
            row = {
                "region": default_region,
                "techname": process["name"],
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
            row = {
                "region": default_region,
                "techname": process["name"],
                "eff": process["efficiency"],
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
                "techname": process["name"],
            }
            if first_output:
                row["commodity-out"] = first_output
            row.update(bound_param)
            topology_rows.append(row)

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

    # Build scenario files (~TFM_INS-TS tables) for commodity_price scenarios
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

    # Build process file - use VT_{region}_ prefix for internal region recognition
    # For multi-region models, use the first region for the file name
    model_name = model.get("name", "Model")
    first_region = regions[0] if regions else "REG1"
    process_file_path = f"VT_{first_region}_{model_name}.xlsx"

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
                "path": "SysSettings/SysSettings.xlsx",
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


# PCG inference order (from xl2times transforms.py line 23)
CSETS_ORDERED_FOR_PCG = ["DEM", "MAT", "NRG", "ENV", "FIN"]


def _infer_primary_commodity_group(
    process: dict, commodities_by_name: dict[str, dict]
) -> str:
    """
    Infer the Primary Commodity Group (PCG) using xl2times rules.

    Algorithm (from xl2times _process_comm_groups_vectorised):
    1. Try OUTPUT commodities first, then INPUT
    2. For each side, try commodity types in order: DEM, MAT, NRG, ENV, FIN
    3. First match wins

    Args:
        process: Process definition from VedaLang source
        commodities_by_name: Dict mapping commodity name to commodity definition

    Returns:
        PCG suffix like "NRGO", "DEMO", "MATI", etc.
    """
    for io_suffix, flow_key in [("O", "outputs"), ("I", "inputs")]:
        flows = process.get(flow_key, [])
        if not flows:
            continue

        flow_csets = set()
        for flow in flows:
            comm_name = flow.get("commodity")
            if comm_name and comm_name in commodities_by_name:
                comm = commodities_by_name[comm_name]
                cset = _commodity_type_to_csets(comm.get("type", "energy"))
                flow_csets.add(cset)

        for cset in CSETS_ORDERED_FOR_PCG:
            if cset in flow_csets:
                return cset + io_suffix

    return "NRGO"


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
    Compile a scenario definition to TableIR rows for ~TFM_INS-TS.

    Expands sparse time-series to dense rows for all model years using
    VEDA-compatible interpolation semantics. No year=0 rows are emitted;
    the compiler handles all interpolation.

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
        interpolation = scenario["interpolation"]  # Required field

        # Expand to all model years using VEDA-compatible interpolation
        dense_values = _expand_series_to_years(
            sparse_values, model_years, interpolation
        )

        # Emit one row per year (canonical long format, dense)
        for year in sorted(dense_values.keys()):
            rows.append({
                "region": region,
                "year": year,
                "pset_co": commodity,
                "cost": dense_values[year],
            })

    # Note: demand_projection is handled separately in compile_vedalang_to_tableir
    # as it emits to ~FI_T table, not ~TFM_INS-TS

    return rows


def _compile_demand_projections(
    scenarios: list[dict],
    region: str,
    model_years: list[int],
) -> list[dict]:
    """
    Compile demand_projection scenarios to TableIR rows for ~FI_T.

    Demand projections use attribute=DEMAND which maps to COM_PROJ in TIMES.

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

        # Emit one row per year with attribute=DEMAND
        for year in sorted(dense_values.keys()):
            rows.append({
                "region": region,
                "attribute": "DEMAND",
                "commodity": commodity,
                "year": year,
                "value": dense_values[year],
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

    Matrix format: sheet name encodes direction (Bi_COMM or Uni_COMM),
    first column is commodity, other columns are destination regions.
    Cell value is explicit process name (NOT numeric 1).

    Process naming follows VEDA convention: T{B|U}_{COMM}_{REG1}_{REG2}_01

    Args:
        trade_links: List of trade link definitions from VedaLang source
        commodities: List of commodity definitions (for unit lookup)

    Returns:
        Tuple of:
        - List of TableIR file definitions
        - List of process declaration rows for ~FI_PROCESS
        - List of topology rows for ~FI_T (input/output flows)
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
    efficiency_rows = []
    process_rows = []  # Explicit trade process declarations
    topology_rows = []  # Trade process topology (inputs/outputs)
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
                        "techname": process_name,
                        "techdesc": f"Trade {commodity} from {origin} to {dest}",
                        "sets": "IRE",
                        "tact": unit,
                        "tcap": "",  # Trade processes typically don't have capacity
                    })

                    # For bidirectional, also declare in destination region
                    if bidirectional:
                        process_rows.append({
                            "region": dest,
                            "techname": process_name,
                            "techdesc": f"Trade {commodity} from {origin} to {dest}",
                            "sets": "IRE",
                            "tact": unit,
                            "tcap": "",
                        })

                    # Emit topology rows - IRE processes need commodity flows
                    # Origin exports (OUT), destination imports (IN)
                    topology_rows.append({
                        "region": origin,
                        "techname": process_name,
                        "commodity-out": commodity,
                    })
                    topology_rows.append({
                        "region": dest,
                        "techname": process_name,
                        "commodity-in": commodity,
                    })

                    emitted_processes.add(process_name)

                # If efficiency specified, emit ~FI_T row for IRE_FLO
                if efficiency is not None:
                    efficiency_rows.append({
                        "region": origin,
                        "techname": process_name,
                        "commodity-out": commodity,
                        "eff": efficiency,
                    })

            rows.append(row)

        tradelink_sheets.append({
            "name": sheet_name,
            "tables": [{"tag": "~TRADELINKS", "rows": rows}],
        })

    # Build trade file with all sheets
    trade_file = {
        "path": "SuppXLS/Trades/ScenTrade__Trade_Links.xlsx",
        "sheets": tradelink_sheets,
    }

    # If we have efficiency rows, add them to a separate sheet
    if efficiency_rows:
        trade_file["sheets"].append({
            "name": "TradeParams",
            "tables": [{"tag": "~FI_T", "rows": efficiency_rows}],
        })

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

    Args:
        timeslices: Timeslice definition from VedaLang source
        regions: List of region codes

    Returns:
        Tuple of (timeslice_rows, yrfr_rows)
    """
    season_codes = [s["code"] for s in timeslices.get("season", [])]
    weekly_codes = [w["code"] for w in timeslices.get("weekly", [])]
    daynite_codes = [d["code"] for d in timeslices.get("daynite", [])]

    # Build ~TIMESLICES rows (Cartesian product of all levels)
    timeslice_rows = []

    # Handle case where some levels are empty
    seasons = season_codes if season_codes else [""]
    weeklies = weekly_codes if weekly_codes else [""]
    daynites = daynite_codes if daynite_codes else [""]

    for season in seasons:
        for weekly in weeklies:
            for daynite in daynites:
                timeslice_rows.append({
                    "season": season,
                    "weekly": weekly,
                    "daynite": daynite,
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

    Emission cap uses:
    - UC_COMPRD with coefficient 1 (LHS side) to sum commodity production
    - UC_RHSRT with the limit value (RHS side)

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
    # This says "include commodity production in the constraint"
    description = f"Emission cap on {commodity}"
    for year in sorted(dense_values.keys()):
        rows.append({
            "uc_n": uc_name,
            "description": description,
            "region": region,
            "year": year,
            "attribute": "UC_COMPRD",
            "commodity": commodity,
            "side": "LHS",
            "value": 1,
        })

    # Emit RHS row: UC_RHSRT with the limit
    for year in sorted(dense_values.keys()):
        rows.append({
            "uc_n": uc_name,
            "description": description,
            "region": region,
            "year": year,
            "attribute": "UC_RHSRT",
            "limtype": limtype,
            "value": dense_values[year],
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
        for process in processes:
            rows.append({
                "uc_n": uc_name,
                "description": description,
                "region": region,
                "year": year,
                "attribute": "UC_ACT",
                "process": process,
                "side": "LHS",
                "value": 1,
            })

        # LHS: Subtract share * commodity production
        rows.append({
            "uc_n": uc_name,
            "description": description,
            "region": region,
            "year": year,
            "attribute": "UC_COMPRD",
            "commodity": commodity,
            "side": "LHS",
            "value": -share,
        })

        # RHS: The bound is 0
        rows.append({
            "uc_n": uc_name,
            "description": description,
            "region": region,
            "year": year,
            "attribute": "UC_RHSRT",
            "limtype": limtype,
            "value": 0,
        })

    return rows


def load_vedalang(path: Path) -> dict:
    """Load VedaLang source from YAML file."""
    with open(path) as f:
        return yaml.safe_load(f)
