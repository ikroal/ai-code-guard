"""Backward-compatibility shim — checker data models moved to ac_guard.domain.

The ``StageOutcome`` / ``CheckResult`` / ``Violation`` dataclasses now live in
:mod:`ac_guard.domain.models` because they are **intermediate result
types** flowing between multiple modules (checker → cli → reporter), not
checker-internal implementation details. See that module's docstring for
the admission criteria of the domain layer.

New code should import from :mod:`ac_guard.domain.models`. This shim
re-exports the old location so existing imports keep working.
"""

from ac_guard.domain.models import CheckResult, StageOutcome, Violation

__all__ = ["CheckResult", "StageOutcome", "Violation"]
