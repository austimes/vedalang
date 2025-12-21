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

    # Build commodity table (~FI_COMM)
    comm_rows = []
    for commodity in model.get("commodities", []):
        comm_rows.append({
            "Csets": _commodity_type_to_csets(commodity.get("type", "energy")),
            "CommName": commodity["name"],
            "Unit": commodity.get("unit", "PJ"),
        })

    # Build process table (~FI_PROCESS)
    process_rows = []
    for process in model.get("processes", []):
        process_rows.append({
            "TechName": process["name"],
            "TechDesc": process.get("description", ""),
            "Sets": ",".join(process.get("sets", [])),
            "Tact": process.get("activity_unit", "PJ"),
            "Tcap": process.get("capacity_unit", "GW"),
        })

    # Build topology table (~FI_T) for inputs/outputs
    topology_rows = []
    for process in model.get("processes", []):
        # Add input flows
        for inp in process.get("inputs", []):
            row = {
                "TechName": process["name"],
                "Comm-IN": inp["commodity"],
            }
            if "share" in inp:
                row["Share-I"] = inp["share"]
            topology_rows.append(row)

        # Add output flows
        for out in process.get("outputs", []):
            row = {
                "TechName": process["name"],
                "Comm-OUT": out["commodity"],
            }
            if "share" in out:
                row["Share-O"] = out["share"]
            topology_rows.append(row)

        # Add efficiency if specified
        if "efficiency" in process:
            topology_rows.append({
                "TechName": process["name"],
                "EFF": process["efficiency"],
            })

    # Build TableIR structure
    tableir = {
        "files": [
            {
                "path": "SysSettings/SysSettings.xlsx",
                "sheets": [
                    {
                        "name": "Commodities",
                        "tables": [{"tag": "~FI_COMM", "rows": comm_rows}],
                    }
                ],
            },
            {
                "path": "SubRES_Model/SubRES_Model.xlsx",
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


def load_vedalang(path: Path) -> dict:
    """Load VedaLang source from YAML file."""
    with open(path) as f:
        return yaml.safe_load(f)
