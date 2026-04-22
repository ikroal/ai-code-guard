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
    """Format a StageOutcome for terminal display.

    Produces a multi-line rendering: stage heading, one ``[PASS]`` /
    ``[FAIL]`` / ``[SKIP]`` indicator per check, inline violation list,
    and a passed/total summary + total elapsed. Serves both CLI users
    and Git-hook environments; callers decide whether to truncate.

    Args:
        report: Any to format.
        locale: Label locale (``"en"`` or ``"zh-CN"``). Unknown locales
            fall back to English. Only full-line headings are localized;
            the ``[PASS] / [FAIL] / [SKIP]`` indicators and check names
            stay as stable ASCII tokens to preserve alignment.

    Returns:
        Formatted multi-line string for terminal output.
    """
    labels = _labels_for(locale)
    status = labels["passed"] if report.passed else labels["failed"]

    lines: list[str] = []
    lines.append(f"{labels['stage']}: {report.stage} — {status}")
    lines.append("")

    for result in report.results:
        indicator = _result_indicator(result)
        duration = f" ({result.duration_ms}ms)" if result.duration_ms else ""
        lines.append(f"  [{indicator}] {result.name}{duration}")
        lines.extend(f"    {_format_violation(v)}" for v in result.violations)

    lines.append("")
    passed = sum(1 for r in report.results if r.passed)
    total = len(report.results)
    failed = total - passed
    lines.append(labels["summary"].format(passed=passed, total=total, failed=failed))

    if report.duration_ms:
        lines.append(f"{labels['total_time']}: {report.duration_ms}ms")

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
    template_name = _LOCALE_TEMPLATES.get(locale, "report_en.md.j2")
    env = _get_env()
    template = env.get_template(template_name)

    violations: list[Any] = []
    for result in report.results:
        violations.extend(result.violations)

    passed = sum(1 for r in report.results if r.passed)
    total = len(report.results)

    return template.render(
        report=report,
        violations=violations,
        passed=passed,
        total=total,
    )


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
