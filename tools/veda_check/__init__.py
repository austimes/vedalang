"""veda_check - unified validation orchestrator for VedaLang models."""

from .checker import CheckResult, run_check

__all__ = ["run_check", "CheckResult"]
