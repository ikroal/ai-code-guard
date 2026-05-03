"""Domain registry for ac-guard's recognized pre-commit lifecycle stages.

ac-guard accepts user-configured hooks under ``code.<stage>`` only for
a finite set of pre-commit lifecycle stages. This module owns that
single source of truth, used by config schema validation to reject
unknown stage keys.

The MODELED-vs-DELEGATED distinction (which stages code_gate runs
itself vs delegates to pre-commit framework) is a *code_gate
implementation choice*, not a property of the stage. It lives in
``code_gate`` privately. Likewise, "format/lint scope" (which stages
make sense for file-typed format/lint hooks) is a *config semantic
rule*'s decision criterion and lives next to that rule. Both concepts
happen to coincide today but are logically independent — they are
deliberately not exposed here.
"""

from __future__ import annotations

__all__ = ["KNOWN_STAGES"]


# Stage names recognized as keys under ``code.<stage>`` in guard.yaml.
# Driving consumer: config/validator.py uses this as the ``key_enum``
# of the ``code`` DynDict to reject typos at schema validation time.
KNOWN_STAGES: frozenset[str] = frozenset(
    {
        "pre-commit",
        "pre-push",
        "commit-msg",
        "pre-merge-commit",
        "pre-rebase",
    }
)
