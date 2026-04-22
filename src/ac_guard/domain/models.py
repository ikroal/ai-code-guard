"""Intermediate result types that flow checker → cli → reporter."""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = ["CheckResult", "StageOutcome", "Violation"]


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
class CheckResult:
    """Result of running a single check or hook.

    Attributes:
        name: Check or hook name.
        passed: Whether the check passed.
        violations: Detailed violation list.
        duration_ms: Execution time in milliseconds.
        output: Captured stdout/stderr for diagnostics.
        skipped: Whether the check was skipped.
    """

    name: str
    passed: bool
    violations: list[Violation] = field(default_factory=list)
    duration_ms: int = 0
    output: str = ""
    skipped: bool = False


@dataclass
class StageOutcome:
    """Outcome of a single check-stage run (one pre-commit / pre-push / ...).

    Attributes:
        stage: Git hook stage label (e.g. "pre-commit", "pre-push").
        passed: Whether all checks in the stage passed.
        results: Per-check results.
        duration_ms: Total execution time in milliseconds.
    """

    stage: str
    passed: bool
    results: list[CheckResult] = field(default_factory=list)
    duration_ms: int = 0
