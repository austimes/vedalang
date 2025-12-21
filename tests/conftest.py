"""Pytest configuration for veda-devtools tests."""

from datetime import date
from pathlib import Path
from typing import Literal

import pytest
import yaml


@pytest.fixture
def fixtures_dir() -> Path:
    """Return the path to the fixtures directory."""
    return Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def rules_dir() -> Path:
    """Return the path to the rules directory."""
    return Path(__file__).parent.parent / "rules"


@pytest.fixture
def failures_dir() -> Path:
    """Return the path to the failures directory."""
    return Path(__file__).parent / "failures"


def record_failure(
    id: str,
    intent: str,
    input_content: str,
    input_format: Literal["vedalang", "tableir"],
    tool: str,
    error_code: str,
    error_message: str,
    failure_type: Literal["A", "B", "C"] = "A",
    resolution: str | None = None,
    test_added: str | None = None,
) -> Path:
    """Record a failure for later analysis.

    Args:
        id: Unique identifier for the failure (used as filename).
        intent: What the agent was trying to accomplish.
        input_content: The input that caused the failure.
        input_format: Format of the input ('vedalang' or 'tableir').
        tool: Which tool produced the error.
        error_code: The error code from the tool.
        error_message: The error message from the tool.
        failure_type: Type of failure:
            - A: Wrong VEDA structure
            - B: VedaLang can't express valid pattern
            - C: Compiler bug
        resolution: How the issue was resolved (optional, added later).
        test_added: Reference to test that was added (optional, added later).

    Returns:
        Path to the created failure record file.
    """
    failures_dir = Path(__file__).parent / "failures"
    failures_dir.mkdir(exist_ok=True)

    record = {
        "id": id,
        "date": date.today().isoformat(),
        "type": failure_type,
        "intent": intent,
        "input": {
            "format": input_format,
            "content": input_content,
        },
        "tool": tool,
        "error": {
            "code": error_code,
            "message": error_message,
        },
    }

    if resolution:
        record["resolution"] = resolution
    if test_added:
        record["test_added"] = test_added

    output_path = failures_dir / f"{id}.yaml"
    with open(output_path, "w") as f:
        yaml.dump(
            record, f, default_flow_style=False, sort_keys=False, allow_unicode=True
        )

    return output_path
