"""Code gate — git hook-time code quality orchestration (K2-K6).

Public API for running ac-guard-controlled code quality checks. This
facade exposes the symbols that constitute the package's contract;
importing from :mod:`ac_guard.code_gate.core` directly is reserved for
white-box tests of internal helpers.
"""

from ac_guard.code_gate.core import (
    StageOptions,
    get_changed_files,
    run_build,
    run_check,
    run_precommit,
    run_stage,
)

__all__ = [
    "StageOptions",
    "get_changed_files",
    "run_build",
    "run_check",
    "run_precommit",
    "run_stage",
]
