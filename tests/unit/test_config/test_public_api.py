"""Snapshot of the :mod:`ac_guard.config` public surface.

Locks down what callers outside the package are allowed to import from
``ac_guard.config``. New additions must be deliberate and accompany an
update to this snapshot; accidental re-exports are caught here.
"""

from __future__ import annotations

import dataclasses

import pytest

import ac_guard.config as config_pkg

EXPECTED_PUBLIC_API: frozenset[str] = frozenset(
    {
        # Entry-point functions
        "resolve_config",
        # Configuration-environment diagnosis entry (IO-bearing, doctor-side).
        "diagnose_config",
        # Output schema tree (S2): 14 dataclasses reachable from ResolvedConfig
        "ResolvedConfig",
        "BehaviorConfig",
        "OperationRules",
        "Rule",
        "CodeConfig",
        "StageBucket",
        "CheckItem",
        "PreCommitHook",
        "PreCommitRepo",
        "PreCommitMeta",
        "LanguageTools",
        "OutputConfig",
        "AuditConfig",
        "PrReportConfig",
        # Diagnostics (runtime_check output)
        "Diagnostic",
        # Error types (Q2 / Q4)
        "ConfigError",
        "ConfigFileNotFoundError",
        "ConfigSyntaxError",
        "ConfigValidationError",
        "ConfigWarning",
        "ValidationIssue",
    }
)


def test_public_api_matches_snapshot() -> None:
    """``__all__`` must match the snapshot above."""
    assert frozenset(config_pkg.__all__) == EXPECTED_PUBLIC_API


def test_all_public_symbols_are_importable() -> None:
    """Every name in ``__all__`` must resolve on the package."""
    missing = [name for name in config_pkg.__all__ if not hasattr(config_pkg, name)]
    assert not missing, f"declared in __all__ but missing: {missing}"


def test_no_duplicate_entries() -> None:
    """``__all__`` must not contain duplicates."""
    assert len(config_pkg.__all__) == len(set(config_pkg.__all__))


_FROZEN_DATACLASSES = (
    "ResolvedConfig",
    "BehaviorConfig",
    "OperationRules",
    "Rule",
    "CodeConfig",
    "StageBucket",
    "CheckItem",
    "PreCommitHook",
    "PreCommitRepo",
    "PreCommitMeta",
    "LanguageTools",
    "OutputConfig",
    "AuditConfig",
    "PrReportConfig",
)


@pytest.mark.parametrize("name", _FROZEN_DATACLASSES)
def test_output_schema_is_frozen(name: str) -> None:
    """Every dataclass in the output schema tree must be frozen (Q3)."""
    cls = getattr(config_pkg, name)
    assert dataclasses.is_dataclass(cls), f"{name} is not a dataclass"
    params = cls.__dataclass_params__  # type: ignore[attr-defined]
    assert params.frozen, f"{name} must be declared with @dataclass(frozen=True)"
