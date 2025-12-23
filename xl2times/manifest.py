"""Manifest generation for xl2times.

This module provides structured manifest output describing what xl2times parsed
and how it interpreted the input. Used by veda-devtools for indexing and validation.
"""

import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .datatypes import DataModule, EmbeddedXlTable, TimesModel


@dataclass
class InputFile:
    """Represents an input file in the manifest."""

    path: str
    module_type: str | None
    module_name: str | None
    submodule: str | None
    table_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "module_type": self.module_type,
            "module_name": self.module_name,
            "submodule": self.submodule,
            "table_count": self.table_count,
        }


@dataclass
class TableEntry:
    """Represents a table in the manifest."""

    id: str
    tag: str
    file: str
    sheet: str
    range: str
    row_count: int
    columns: list[str]
    tag_variant: str | None = None
    defaults: str | None = None
    uc_sets: dict[str, str] | None = None
    status: str = "processed"
    drop_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result = {
            "id": self.id,
            "tag": self.tag,
            "file": self.file,
            "sheet": self.sheet,
            "range": self.range,
            "row_count": self.row_count,
            "columns": self.columns,
            "status": self.status,
        }
        if self.tag_variant:
            result["tag_variant"] = self.tag_variant
        if self.defaults:
            result["defaults"] = self.defaults
        if self.uc_sets:
            result["uc_sets"] = self.uc_sets
        if self.drop_reason:
            result["drop_reason"] = self.drop_reason
        return result


@dataclass
class Symbol:
    """Represents a model symbol (process, commodity, etc.)."""

    name: str
    description: str | None = None
    defined_in: str | None = None
    regions: list[str] | None = None
    sets: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"name": self.name}
        if self.description:
            result["description"] = self.description
        if self.defined_in:
            result["defined_in"] = self.defined_in
        if self.regions:
            result["regions"] = self.regions
        if self.sets:
            result["sets"] = self.sets
        return result


class ManifestBuilder:
    """Builds a manifest from xl2times processing."""

    def __init__(self, case: str | None = None):
        self._case = case
        self._input_files: dict[str, InputFile] = {}
        self._tables: list[TableEntry] = []
        self._dropped_tables: list[TableEntry] = []

    def add_input_file(self, path: str):
        """Register an input file."""
        if path in self._input_files:
            return

        self._input_files[path] = InputFile(
            path=path,
            module_type=DataModule.module_type(path),
            module_name=DataModule.module_name(path),
            submodule=DataModule.submodule(path),
            table_count=0,
        )

    def add_table(self, table: EmbeddedXlTable, status: str = "processed", drop_reason: str | None = None):
        """Add a table to the manifest."""
        # Generate a unique ID for this table
        table_id = f"T-{uuid.uuid4().hex[:8]}"

        # Parse tag variant (e.g., ~TFM_INS-TS -> variant is "-TS")
        tag_variant = None
        tag_parts = table.tag.split("-", 1)
        if len(tag_parts) > 1 and tag_parts[0] in ["~TFM_INS", "~TFM_UPD", "~TFM_DINS"]:
            tag_variant = f"-{tag_parts[1]}"

        entry = TableEntry(
            id=table_id,
            tag=table.tag,
            file=table.filename,
            sheet=table.sheetname,
            range=table.range,
            row_count=len(table.dataframe),
            columns=list(table.dataframe.columns),
            tag_variant=tag_variant,
            defaults=table.defaults,
            uc_sets=table.uc_sets if table.uc_sets else None,
            status=status,
            drop_reason=drop_reason,
        )

        if status == "dropped":
            self._dropped_tables.append(entry)
        else:
            self._tables.append(entry)

        # Increment table count for the source file
        if table.filename in self._input_files:
            self._input_files[table.filename].table_count += 1

    def add_tables_from_list(self, tables: list[EmbeddedXlTable]):
        """Add multiple tables from a list."""
        for table in tables:
            self.add_input_file(table.filename)
            self.add_table(table)

    def build_symbols(self, model: TimesModel) -> dict[str, Any]:
        """Extract symbols from the TimesModel."""
        symbols: dict[str, Any] = {}

        # Processes
        if not model.processes.empty:
            processes = []
            for _, row in model.processes.iterrows():
                proc_name = row.get("process", "")
                proc_desc = row.get("description") if "description" in row else None
                proc_sets_val = row.get("sets") if "sets" in row else None
                proc_sets = [str(proc_sets_val)] if proc_sets_val else None
                proc = Symbol(
                    name=str(proc_name) if proc_name else "",
                    description=str(proc_desc) if proc_desc else None,
                    sets=proc_sets,
                )
                processes.append(proc.to_dict())
            symbols["processes"] = processes

        # Commodities
        if not model.commodities.empty:
            commodities = []
            for _, row in model.commodities.iterrows():
                comm_name = row.get("commodity", "")
                comm_desc = row.get("description") if "description" in row else None
                comm_sets_val = row.get("csets") if "csets" in row else None
                comm_sets = [str(comm_sets_val)] if comm_sets_val else None
                comm = Symbol(
                    name=str(comm_name) if comm_name else "",
                    description=str(comm_desc) if comm_desc else None,
                    sets=comm_sets,
                )
                commodities.append(comm.to_dict())
            symbols["commodities"] = commodities

        # Regions
        if model.all_regions:
            symbols["regions"] = sorted(list(model.all_regions))

        # User constraints
        if not model.user_constraints.empty and "uc_n" in model.user_constraints.columns:
            uc_names = model.user_constraints["uc_n"].unique().tolist()
            symbols["user_constraints"] = [{"name": name} for name in uc_names]

        return symbols

    def build_time_horizon(self, model: TimesModel) -> dict[str, Any] | None:
        """Extract time horizon information."""
        result = {}

        if model.start_year:
            result["start_year"] = model.start_year

        if not model.time_periods.empty and "m" in model.time_periods.columns:
            result["milestone_years"] = sorted(model.time_periods["m"].tolist())

        return result if result else None

    def to_dict(self, model: TimesModel, xl2times_version: str = "unknown") -> dict[str, Any]:
        """Build the complete manifest dictionary."""
        manifest: dict[str, Any] = {
            "version": "1.0.0",
            "xl2times_version": xl2times_version,
            "timestamp": datetime.now().isoformat(),
        }

        if self._case:
            manifest["case"] = self._case

        manifest["inputs"] = [f.to_dict() for f in self._input_files.values()]
        manifest["tables"] = [t.to_dict() for t in self._tables]

        # Include dropped tables with their reasons
        if self._dropped_tables:
            manifest["tables"].extend([t.to_dict() for t in self._dropped_tables])

        # Build symbols from model
        symbols = self.build_symbols(model)
        if symbols:
            manifest["symbols"] = symbols

        # Data modules
        if model.data_modules:
            manifest["data_modules"] = model.data_modules

        # Time horizon
        time_horizon = self.build_time_horizon(model)
        if time_horizon:
            manifest["time_horizon"] = time_horizon

        return manifest

    def write_json(self, path: str | Path, model: TimesModel, xl2times_version: str = "unknown"):
        """Write manifest to a JSON file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(model, xl2times_version), f, indent=2)
