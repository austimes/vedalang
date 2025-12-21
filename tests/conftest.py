"""Pytest configuration for veda-devtools tests."""

from pathlib import Path

import pytest


@pytest.fixture
def fixtures_dir() -> Path:
    """Return the path to the fixtures directory."""
    return Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def rules_dir() -> Path:
    """Return the path to the rules directory."""
    return Path(__file__).parent.parent / "rules"
