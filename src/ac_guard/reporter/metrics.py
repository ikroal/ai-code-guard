"""Metrics extraction and enrichment for PR quality reports.

Post-processes :class:`CheckResult.output` to extract structured metrics
(coverage %, test counts, docstring %, etc.) without affecting the
pass/fail determination (which remains exit-code-only per ADR-4).

Also provides checklist building and guard-system file change detection.
"""

from __future__ import annotations

import re
import subprocess
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

    from ac_guard.domain.models import StageOutcome

from dataclasses import dataclass

from ac_guard.domain.models import CheckMetrics


@dataclass
class ChecklistItem:
    """A single item in the quality checklist.

    Attributes:
        label: Human-readable label (e.g. "Code formatting").
        status: Pass/fail/skip/warn status.
        detail: Optional detail string (e.g. "85%", "129/129").
    """

    label: str
    status: str  # "pass", "fail", "skip", "warn"
    detail: str = ""


__all__ = ["ChecklistItem", "build_checklist", "enrich_outcome"]

# ---------------------------------------------------------------------------
# Parser registry
# ---------------------------------------------------------------------------

_PARSERS: list[Callable[[str, str], CheckMetrics | None]] = []


def _register_parser(fn: Callable[[str, str], CheckMetrics | None]) -> None:
    """Register a metrics parser. Called at module import time."""
    _PARSERS.append(fn)


def _extract_metrics(name: str, output: str) -> CheckMetrics | None:
    """Try all registered parsers, return first match."""
    for parser in _PARSERS:
        result = parser(name, output)
        if result is not None:
            return result
    return None


# ---------------------------------------------------------------------------
# Built-in parsers
# ---------------------------------------------------------------------------

# pytest summary line: "129 passed", "128 passed, 1 failed, 2 skipped"
_PYTEST_SUMMARY_RE = re.compile(
    r"(\d+)\s+passed"
    r"(?:,\s*(\d+)\s+failed)?"
    r"(?:,\s*(\d+)\s+skipped)?"
)

# coverage.py TOTAL line: "TOTAL    1234    567    85%"
_COVERAGE_TOTAL_RE = re.compile(r"TOTAL\s+\d+\s+\d+\s+(\d+)%")


def _parse_pytest(name: str, output: str) -> CheckMetrics | None:
    """Parse pytest output for test counts and coverage."""
    match = _PYTEST_SUMMARY_RE.search(output)
    if not match:
        return None

    passed = int(match.group(1))
    failed = int(match.group(2) or 0)
    skipped = int(match.group(3) or 0)
    total = passed + failed + skipped

    coverage_match = _COVERAGE_TOTAL_RE.search(output)
    coverage_pct = float(coverage_match.group(1)) if coverage_match else None

    return CheckMetrics(
        tests_total=total,
        tests_passed=passed,
        tests_failed=failed,
        tests_skipped=skipped,
        coverage_pct=coverage_pct,
    )


_register_parser(_parse_pytest)


# interrogate output: "RESULT: PASSED (100.0%)"
_INTERROGATE_RESULT_RE = re.compile(r"RESULT:\s*\w+\s*\((\d+\.?\d*)%\)")


def _parse_interrogate(name: str, output: str) -> CheckMetrics | None:
    """Parse interrogate output for docstring coverage percentage."""
    match = _INTERROGATE_RESULT_RE.search(output)
    if not match:
        return None
    return CheckMetrics(docstring_pct=float(match.group(1)))


_register_parser(_parse_interrogate)


# Matches ruff output: "Found 3 errors."
_RUFF_ERRORS_RE = re.compile(r"Found\s+(\d+)\s+error")


def _parse_ruff(name: str, output: str) -> CheckMetrics | None:
    """Parse ruff output for lint issue count."""
    match = _RUFF_ERRORS_RE.search(output)
    if not match:
        return None
    count = int(match.group(1))
    if count == 0:
        return None
    return CheckMetrics(static_analysis_issues=count)


_register_parser(_parse_ruff)


# bandit: "Total issues (by severity): ... High: 0 ... Low: 2"
_BANDIT_TOTAL_RE = re.compile(
    r"Total issues.*?High:\s*(\d+).*?Low:\s*(\d+)",
    re.DOTALL,
)


def _parse_bandit(name: str, output: str) -> CheckMetrics | None:
    """Parse bandit output for security issue count."""
    match = _BANDIT_TOTAL_RE.search(output)
    if not match:
        return None
    high = int(match.group(1))
    low = int(match.group(2))
    total = high + low
    if total == 0:
        return None
    return CheckMetrics(static_analysis_issues=total)


_register_parser(_parse_bandit)


# ---------------------------------------------------------------------------
# Checklist builder
# ---------------------------------------------------------------------------

_STATUS_EMOJI = {
    "pass": "✅",
    "fail": "❌",
    "skip": "⏭️",
    "warn": "⚠️",
}


def build_checklist(outcome: StageOutcome) -> list[ChecklistItem]:
    """Build a human-readable quality checklist from check results."""
    items: list[ChecklistItem] = []

    for result in outcome.results:
        if result.skipped:
            continue

        # Map check names to semantic labels
        label = _check_label(result.name)
        if label is None:
            continue

        # Determine status and detail
        if result.metrics:
            if result.metrics.coverage_pct is not None:
                status = "pass" if result.passed else "fail"
                detail = f"{result.metrics.coverage_pct:.0f}%"
            elif result.metrics.tests_total is not None:
                status = "pass" if result.passed else "fail"
                m = result.metrics
                detail = f"{m.tests_passed}/{m.tests_total}"
            elif result.metrics.docstring_pct is not None:
                status = "pass" if result.passed else "fail"
                detail = f"{result.metrics.docstring_pct:.0f}%"
            elif result.metrics.static_analysis_issues is not None:
                status = "fail" if result.metrics.static_analysis_issues > 0 else "pass"
                detail = f"{result.metrics.static_analysis_issues} issues"
            else:
                status = "pass" if result.passed else "fail"
                detail = ""
        else:
            status = "pass" if result.passed else "fail"
            detail = ""

        items.append(ChecklistItem(label=label, status=status, detail=detail))

    return items


def _check_label(name: str) -> str | None:
    """Map a check name to a human-readable label, or None to skip."""
    lower = name.lower()
    if "format" in lower:
        return "Code formatting"
    if "lint" in lower:
        return "Linting"
    if "test" in lower or "pytest" in lower:
        return "Tests"
    if "coverage" in lower:
        return "Coverage"
    if "interrogate" in lower or "docstring" in lower:
        return "Docstring coverage"
    if "bandit" in lower or "security" in lower:
        return "Security analysis"
    if "build" in lower:
        return "Build"
    if "forbid-noqa" in lower or "encoding" in lower:
        return "Code quality"
    return None


# ---------------------------------------------------------------------------
# Guard-system file change detection
# ---------------------------------------------------------------------------

_GUARD_FILE_PATTERNS = [
    "guard.yaml",
    ".pre-commit-config.yaml",
    ".ac-guard/",
    ".git/hooks/",
    ".claude/",
    ".cursor/",
    "pyproject.toml",
]


def _detect_guard_changes(project_root: str | None = None) -> list[str]:
    """Detect guard-system files changed in this branch vs main."""
    try:
        result = subprocess.run(
            ["git", "diff", "origin/main..HEAD", "--name-only"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
            cwd=project_root,
        )
        if result.returncode != 0:
            return []
        changed = [f for f in result.stdout.strip().split("\n") if f]
        return [
            f for f in changed if any(pattern in f for pattern in _GUARD_FILE_PATTERNS)
        ]
    except (subprocess.TimeoutExpired, OSError):
        return []


# ---------------------------------------------------------------------------
# Enrichment entry point
# ---------------------------------------------------------------------------


def enrich_outcome(outcome: StageOutcome) -> StageOutcome:
    """Enrich a StageOutcome with metrics and change detection.

    This is the single entry point called by the formatter before
    template rendering. It is idempotent — calling it twice on the
    same outcome is safe (metrics are only extracted if not already set).
    """
    # Extract metrics for each check result
    for result in outcome.results:
        if result.metrics is not None:
            continue  # Already enriched
        if result.output:
            result.metrics = _extract_metrics(result.name, result.output)

    # Detect guard-system file changes
    if not outcome.guard_files_changed:
        outcome.guard_files_changed = _detect_guard_changes()

    # Set generation timestamp
    if not outcome.generated_at:
        outcome.generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    return outcome
