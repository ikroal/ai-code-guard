"""Action guard module — runtime behavior policy enforcement.

Public API: ``evaluate()`` is the sole entry point; ``PolicyDecision``
is its return type; ``Decision`` is the decision enum;
``ActionGuardError`` / ``PolicyCorruptError`` are the user-facing
exceptions.

Internal primitives (``classify``, ``load_policy``, matcher functions)
remain in their submodules but are not re-exported. Tests import them
via deep submodule paths.
"""

from ac_guard.action_guard.core import evaluate
from ac_guard.action_guard.exceptions import ActionGuardError, PolicyCorruptError
from ac_guard.action_guard.matcher import Decision, PolicyDecision

__all__ = [
    "ActionGuardError",
    "Decision",
    "PolicyCorruptError",
    "PolicyDecision",
    "evaluate",
]
