"""Diagnostics collection and output for xl2times.

This module provides structured diagnostic output for veda-devtools integration.
Diagnostics are collected during parsing and transformation, then written to JSON.
"""

import json
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any


class Severity(str, Enum):
    """Diagnostic severity levels."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class SourceLocation:
    """Location reference in an Excel file."""

    file: str | None = None
    sheet: str | None = None
    range: str | None = None
    tag: str | None = None
    row: int | None = None
    column: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass
class Diagnostic:
    """A single diagnostic message."""

    severity: Severity
    code: str
    message: str
    source: SourceLocation | None = None
    context: dict[str, Any] | None = None
    suggestion: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "severity": self.severity.value,
            "code": self.code,
            "message": self.message,
        }
        if self.source:
            result["source"] = self.source.to_dict()
        if self.context:
            result["context"] = self.context
        if self.suggestion:
            result["suggestion"] = self.suggestion
        return result


class DiagnosticsCollector:
    """Collects diagnostics during xl2times processing.

    This is a singleton-like collector that gathers diagnostics from
    various parts of the codebase for later serialization to JSON.
    """

    def __init__(self):
        self._diagnostics: list[Diagnostic] = []
        self._enabled: bool = False

    def enable(self):
        """Enable diagnostic collection."""
        self._enabled = True
        self._diagnostics = []

    def disable(self):
        """Disable diagnostic collection."""
        self._enabled = False

    @property
    def enabled(self) -> bool:
        return self._enabled

    def add(
        self,
        severity: Severity,
        code: str,
        message: str,
        *,
        file: str | None = None,
        sheet: str | None = None,
        range: str | None = None,
        tag: str | None = None,
        row: int | None = None,
        column: str | None = None,
        context: dict[str, Any] | None = None,
        suggestion: str | None = None,
    ):
        """Add a diagnostic to the collection."""
        if not self._enabled:
            return

        source = None
        if any([file, sheet, range, tag, row, column]):
            source = SourceLocation(
                file=file, sheet=sheet, range=range, tag=tag, row=row, column=column
            )

        self._diagnostics.append(
            Diagnostic(
                severity=severity,
                code=code,
                message=message,
                source=source,
                context=context,
                suggestion=suggestion,
            )
        )

    def error(self, code: str, message: str, **kwargs):
        """Add an error diagnostic."""
        self.add(Severity.ERROR, code, message, **kwargs)

    def warning(self, code: str, message: str, **kwargs):
        """Add a warning diagnostic."""
        self.add(Severity.WARNING, code, message, **kwargs)

    def info(self, code: str, message: str, **kwargs):
        """Add an info diagnostic."""
        self.add(Severity.INFO, code, message, **kwargs)

    def get_status(self) -> str:
        """Get overall status based on collected diagnostics."""
        severities = {d.severity for d in self._diagnostics}
        if Severity.ERROR in severities:
            return "error"
        if Severity.WARNING in severities:
            return "warning"
        return "success"

    def get_summary(self) -> dict[str, int]:
        """Get counts by severity."""
        return {
            "error_count": sum(1 for d in self._diagnostics if d.severity == Severity.ERROR),
            "warning_count": sum(1 for d in self._diagnostics if d.severity == Severity.WARNING),
            "info_count": sum(1 for d in self._diagnostics if d.severity == Severity.INFO),
        }

    def to_dict(self, xl2times_version: str = "unknown") -> dict[str, Any]:
        """Convert diagnostics to dictionary for JSON serialization."""
        return {
            "version": "1.0.0",
            "status": self.get_status(),
            "xl2times_version": xl2times_version,
            "timestamp": datetime.now().isoformat(),
            "diagnostics": [d.to_dict() for d in self._diagnostics],
            "summary": self.get_summary(),
        }

    def write_json(self, path: str | Path, xl2times_version: str = "unknown"):
        """Write diagnostics to a JSON file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(xl2times_version), f, indent=2)


# Global collector instance
_collector = DiagnosticsCollector()


def get_collector() -> DiagnosticsCollector:
    """Get the global diagnostics collector."""
    return _collector


def reset_collector():
    """Reset the global collector (mainly for testing)."""
    global _collector
    _collector = DiagnosticsCollector()
