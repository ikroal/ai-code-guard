"""Config package: the single interpreter of ``guard.yaml`` for ac-guard.

This is the only place in the system that parses configuration inputs
(``guard.yaml``, rulesets, built-in defaults) and turns them into a
typed, validated, hash-stable, immutable :class:`ResolvedConfig` value
that downstream modules consume.

Entry points
------------
``resolve_config(path, rulesets=None) -> ResolvedConfig``
    Main entry. Loads, merges, validates, and hashes.
``load_config(path) -> RawConfig``
    Raw pass-through: parse + validate a single file, no merge.
``validate_raw_config(data, source="guard.yaml") -> None``
    In-memory validation for dicts that did not come from ``load_config``.

Schemas
-------
- ``RawConfig`` (input): the ``guard.yaml`` structure.
- ``ResolvedConfig`` (output): the merged value tree. The 13 nested
  dataclasses (``BehaviorConfig``, ``OperationRules``, ``Rule``,
  ``CodeConfig``, ``StageBucket``, ``CheckItem``, ``PreCommitHook``,
  ``PreCommitRepo``, ``PreCommitMeta``, ``LanguageTools``,
  ``OutputConfig``, ``AuditConfig``, ``PrReportConfig``) are all part
  of the public type contract so callers can type-annotate freely.

Errors
------
- ``ConfigError``: base class; catch this to cover any config failure.
- ``ConfigFileNotFoundError``: missing ``guard.yaml``.
- ``ConfigSyntaxError``: YAML syntax / parse failure (carries line/column).
- ``ConfigValidationError``: schema or semantic failure; ``.errors``
  carries a ``list[ValidationIssue]``.
- ``ConfigWarning``: non-fatal merge warnings emitted via
  :mod:`warnings` (e.g. ``remove`` target missing or protected).
- ``ValidationIssue``: structured error payload (``path``, ``message``,
  ``value``).

Import discipline
-----------------
Everything intended for cross-module use lives in this package's
``__all__``. The submodules (``loader``, ``merger``, ``validator``,
``models``, ``exceptions``) are internal — downstream code must import
from :mod:`ac_guard.config` directly.
"""

from ac_guard.config.exceptions import (
    ConfigError,
    ConfigFileNotFoundError,
    ConfigSyntaxError,
    ConfigValidationError,
    ConfigWarning,
    ValidationIssue,
)
from ac_guard.config.loader import RawConfig, load_config
from ac_guard.config.merger import resolve_config
from ac_guard.config.models import (
    AuditConfig,
    BehaviorConfig,
    CheckItem,
    CodeConfig,
    LanguageTools,
    OperationRules,
    OutputConfig,
    PreCommitHook,
    PreCommitMeta,
    PreCommitRepo,
    PrReportConfig,
    ResolvedConfig,
    Rule,
    StageBucket,
)
from ac_guard.config.runtime_check import Diagnostic, runtime_check
from ac_guard.config.validator import validate_raw_config

__all__ = [
    # Entry-point functions
    "resolve_config",
    "load_config",
    "validate_raw_config",
    "runtime_check",
    # Input schema
    "RawConfig",
    # Output schema tree (14 dataclasses reachable from ResolvedConfig)
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
    # Diagnostics (runtime-check output)
    "Diagnostic",
    # Error types
    "ConfigError",
    "ConfigFileNotFoundError",
    "ConfigSyntaxError",
    "ConfigValidationError",
    "ConfigWarning",
    "ValidationIssue",
]
