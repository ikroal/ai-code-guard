"""Code gate — git hook-time code quality orchestration (K2-K6)."""

from ac_guard.code_gate.core import (
    get_changed_files,
    run_build,
    run_check,
    run_precommit,
    run_stage,
)
from ac_guard.domain.models import CheckResult, StageOutcome, Violation

__all__ = [
    "CheckResult",
    "StageOutcome",
    "Violation",
    "get_changed_files",
    "run_build",
    "run_check",
    "run_precommit",
    "run_stage",
]
