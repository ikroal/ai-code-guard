"""Cross-module intermediate Value Objects (pure DTOs).

Admission criteria for types in this module are documented in
``ac_guard/domain/__init__.py``. Transformational behaviour (string
rewriting, protocol helpers, etc.) does NOT belong here — it lives as
a Domain Service in its own sub-module (e.g. ``managed_block.py``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "CheckMetrics",
    "CheckResult",
    "FileSpec",
    "StageOutcome",
    "Violation",
]


@dataclass
class Violation:
    """A single code quality violation found during checking.

    Attributes:
        file: File path where the violation was found.
        line: Line number (1-based), or None if unknown.
        column: Column number (1-based), or None if unknown.
        severity: Severity level ("error", "warning", "info").
        code: Rule code or identifier (e.g., "E501").
        message: Human-readable description of the violation.
        source: Tool that reported this violation.
    """

    file: str
    line: int | None = None
    column: int | None = None
    severity: str = "error"
    code: str = ""
    message: str = ""
    source: str = ""


@dataclass
class CheckMetrics:
    """Structured metrics extracted from a check's raw output.

    All fields are optional; only populated when the corresponding
    tool output is detected and parsed.

    Attributes:
        coverage_pct: Code coverage percentage (from pytest-cov).
        tests_total: Total number of tests.
        tests_passed: Number of passed tests.
        tests_failed: Number of failed tests.
        tests_skipped: Number of skipped tests.
        docstring_pct: Docstring coverage percentage (from interrogate).
        static_analysis_issues: Number of static analysis issues found.
        extra: Tool-specific metrics that don't have dedicated fields.
    """

    coverage_pct: float | None = None
    tests_total: int | None = None
    tests_passed: int | None = None
    tests_failed: int | None = None
    tests_skipped: int | None = None
    docstring_pct: float | None = None
    static_analysis_issues: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class CheckResult:
    """Result of running a single check or hook.

    Attributes:
        name: Check or hook name.
        passed: Whether the check passed.
        violations: Detailed violation list.
        duration_ms: Execution time in milliseconds.
        output: Captured stdout/stderr for diagnostics.
        skipped: Whether the check was skipped.
        metrics: Structured metrics extracted from output.
    """

    name: str
    passed: bool
    violations: list[Violation] = field(default_factory=list)
    duration_ms: int = 0
    output: str = ""
    skipped: bool = False
    metrics: CheckMetrics | None = None


@dataclass
class StageOutcome:
    """Outcome of a single check-stage run (one pre-commit / pre-push / ...).

    Attributes:
        stage: Git hook stage label (e.g. "pre-commit", "pre-push").
        passed: Whether all checks in the stage passed.
        results: Per-check results.
        duration_ms: Total execution time in milliseconds.
        guard_files_changed: Guard system files changed in this PR.
        generated_at: Formatted timestamp of report generation.
    """

    stage: str
    passed: bool
    results: list[CheckResult] = field(default_factory=list)
    duration_ms: int = 0
    guard_files_changed: list[str] = field(default_factory=list)
    generated_at: str = ""


@dataclass
class FileSpec:
    """A file to be generated and written to disk.

    Attributes:
        path: File path relative to project root.
        content: Full file content as string (markers included if applicable).
        executable: Whether the file should have executable permissions.

    Construction:
        - Direct: ``FileSpec(path, content, executable=False)`` — when the
          caller already has the full on-disk content.
        - Managed block: ``managed_block.file_spec(path, body)`` — when the
          caller has the body text that should be wrapped in ac-guard
          managed-block markers. (Lives in ``ac_guard.domain.managed_block``
          since the wrap behaviour is a Domain Service on the managed-block
          protocol, not intrinsic to FileSpec.)
    """

    path: str
    content: str
    executable: bool = False
