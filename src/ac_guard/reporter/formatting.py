"""Reporter formatting — terminal, gate, Markdown, and JSON output.

Converts StageOutcome into human-readable formats for terminal
display, Git Hook output, PR comment rendering, and machine-readable
JSON for CI/CD pipelines.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import TYPE_CHECKING

from jinja2 import Environment, FileSystemLoader

if TYPE_CHECKING:
    from typing import Any

__all__ = ["format_json", "format_markdown", "format_terminal"]

_TEMPLATE_DIR = Path(__file__).parent / "_templates"

# Jinja2 environment (singleton)
_jinja_env: Environment | None = None

_LOCALE_TEMPLATES = {
    "en": "report_en.md.j2",
    "zh-CN": "report_zh_cn.md.j2",
}

# Terminal-facing labels. See format_terminal() docstring for the scope
# of what is localized versus left as stable ASCII tokens.
_LABELS: dict[str, dict[str, str]] = {
    "en": {
        "stage": "Stage",
        "passed": "PASSED",
        "failed": "FAILED",
        "summary": "{passed}/{total} checks passed, {failed} failed",
        "total_time": "Total time",
    },
    "zh-CN": {
        "stage": "阶段",
        "passed": "通过",
        "failed": "失败",
        "summary": "{passed}/{total} 项检查通过, {failed} 项失败",
        "total_time": "总耗时",
    },
}


def _labels_for(locale: str) -> dict[str, str]:
    """Return the label set for *locale*, falling back to English."""
    return _LABELS.get(locale, _LABELS["en"])


def _get_env() -> Environment:
    """Get or create Jinja2 environment."""
    global _jinja_env
    if _jinja_env is None:
        _jinja_env = Environment(
            loader=FileSystemLoader(_TEMPLATE_DIR),
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True,
        )
    return _jinja_env


# ---------------------------------------------------------------------------
# R1: Terminal format
# ---------------------------------------------------------------------------


def format_terminal(report: Any, locale: str = "en") -> str:
    """Format a StageOutcome for terminal display with emojis and metrics.

    Produces a multi-line rendering with enriched data: checklist,
    metrics summary per check, and guard-file change detection.

    Args:
        report: Any to format.
        locale: Label locale (``"en"`` or ``"zh-CN"``).

    Returns:
        Formatted multi-line string for terminal output.
    """
    from ac_guard.reporter.metrics import build_checklist, enrich_outcome

    enriched = enrich_outcome(report)
    checklist = build_checklist(enriched)

    labels = _labels_for(locale)
    status_emoji = "✅" if enriched.passed else "❌"
    status = labels["passed"] if enriched.passed else labels["failed"]

    lines: list[str] = []
    lines.append(f"🤖 {labels['stage']}: {enriched.stage} — {status_emoji} {status}")
    lines.append("")

    # Checklist
    if checklist:
        lines.append("📋 Checklist:")
        for item in checklist:
            emoji = _status_emoji(item.status)
            detail = f" {item.detail}" if item.detail else ""
            lines.append(f"  {emoji} {item.label}{detail}")
        lines.append("")

    # Results
    lines.append("📊 Results:")
    for result in enriched.results:
        emoji = _status_emoji(
            "skip" if result.skipped else ("pass" if result.passed else "fail")
        )
        duration = f" ({result.duration_ms}ms)" if result.duration_ms else ""
        metrics = _metrics_summary(result)
        metrics_str = f" | {metrics}" if metrics else ""
        lines.append(f"  {emoji} {result.name}{duration}{metrics_str}")
        lines.extend(f"    {_format_violation(v)}" for v in result.violations)

    lines.append("")
    passed = sum(1 for r in enriched.results if r.passed)
    total = len(enriched.results)
    failed = total - passed
    lines.append(labels["summary"].format(passed=passed, total=total, failed=failed))

    if enriched.duration_ms:
        lines.append(f"{labels['total_time']}: {enriched.duration_ms}ms")

    # Guard file changes
    if enriched.guard_files_changed:
        lines.append("")
        lines.append(
            f"🔧 Guard files changed: {', '.join(enriched.guard_files_changed)}"
        )

    return "\n".join(lines)


def _result_indicator(result: object) -> str:
    """Return status indicator for a CheckResult.

    Args:
        result: CheckResult-like object with passed/skipped attrs.

    Returns:
        "PASS", "FAIL", or "SKIP".
    """
    if getattr(result, "skipped", False):
        return "SKIP"
    return "PASS" if result.passed else "FAIL"  # type: ignore[union-attr]


def _format_violation(v: Any) -> str:
    """Format a single violation for terminal display.

    Args:
        v: Any to format.

    Returns:
        Formatted violation string.
    """
    loc = v.file
    if v.line is not None:
        loc += f":{v.line}"
        if v.column is not None:
            loc += f":{v.column}"
    msg = f"{loc}: {v.message}" if v.message else loc
    if v.code:
        msg += f" [{v.code}]"
    return msg


# ---------------------------------------------------------------------------
# Markdown format
# ---------------------------------------------------------------------------

_MARKER = "<!-- ac-guard-report -->"
"""Hidden HTML marker prepended to PR comments for update-or-create."""


def format_markdown(
    report: Any,
    locale: str = "en",
) -> str:
    """Format a StageOutcome as Markdown using Jinja2 templates.

    Args:
        report: Any to format.
        locale: Locale for template selection ("en" or "zh-CN").

    Returns:
        Markdown-formatted string.
    """
    from ac_guard.reporter.metrics import build_checklist, enrich_outcome

    enriched = enrich_outcome(report)
    checklist = build_checklist(enriched)

    template_name = _LOCALE_TEMPLATES.get(locale, "report_en.md.j2")
    env = _get_env()
    template = env.get_template(template_name)

    violations: list[Any] = []
    for result in enriched.results:
        violations.extend(result.violations)

    passed = sum(1 for r in enriched.results if r.passed)
    total = len(enriched.results)

    rendered = template.render(
        report=enriched,
        violations=violations,
        passed=passed,
        total=total,
        checklist=checklist,
        guard_files_changed=enriched.guard_files_changed,
        generated_at=enriched.generated_at,
        status_emoji=_status_emoji,
        metrics_summary=_metrics_summary,
    )
    return _MARKER + "\n" + rendered


def _status_emoji(status: str) -> str:
    """Map status string to emoji."""
    return {"pass": "✅", "fail": "❌", "skip": "⏭️", "warn": "⚠️"}.get(status, "")


def _metrics_summary(result: Any) -> str:
    """Render compact metrics summary for a check result."""
    if not result.metrics:
        return ""
    m = result.metrics
    parts = []
    if m.coverage_pct is not None:
        parts.append(f"cov: {m.coverage_pct:.0f}%")
    if m.tests_total is not None:
        parts.append(f"{m.tests_passed}/{m.tests_total} tests")
    if m.docstring_pct is not None:
        parts.append(f"docs: {m.docstring_pct:.0f}%")
    if m.static_analysis_issues is not None:
        parts.append(f"{m.static_analysis_issues} issues")
    return " | ".join(parts)


# ---------------------------------------------------------------------------
# JSON Output
# ---------------------------------------------------------------------------


def format_json(report: Any) -> str:
    """Serialize a StageOutcome to JSON for CI/CD pipelines.

    Uses ``dataclasses.asdict()`` to convert the entire report tree
    (StageOutcome → CheckResult → Violation) into a JSON string.

    Args:
        report: A StageOutcome instance.

    Returns:
        Pretty-printed JSON string parseable by ``jq``.
    """
    return json.dumps(dataclasses.asdict(report), indent=2)
