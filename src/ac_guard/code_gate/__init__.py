"""Code gate — git lifecycle code quality orchestration.

Public contract: two domain operations (``gate_stage`` / ``gate_check``)
that run a quality contract slice and return a verdict-bearing
``StageOutcome``. Importing from :mod:`ac_guard.code_gate.core` is
reserved for white-box tests of internal helpers.
"""

from ac_guard.code_gate.core import (
    GateOptions,
    gate_check,
    gate_stage,
    is_modeled_stage,
)
from ac_guard.domain.models import CheckResult, StageOutcome

__all__ = [
    "CheckResult",
    "GateOptions",
    "StageOutcome",
    "gate_check",
    "gate_stage",
    "is_modeled_stage",
]
