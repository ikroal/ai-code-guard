"""Reporter formatting — terminal, gate, and Markdown output.

Converts CheckReport into human-readable formats for terminal
display, Git Hook output, and PR comment rendering.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from jinja2 import Environment, FileSystemLoader

if TYPE_CHECKING:
    from typing import Any

__all__ = ["format_gate", "format_markdown", "format_terminal"]

_TEMPLATE_DIR = Path(__file__).parent / "_templates"

# Jinja2 environment (singleton)
_jinja_env: Environment | None = None

_LOCALE_TEMPLATES = {
    "en": "report_en.md.j2",
    "zh-CN": "report_zh_cn.md.j2",
}


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


def format_terminal(
    report: Any,
    verbosity: str = "normal",
) -> str:
    """Format a CheckReport for terminal display.

    Args:
        report: Any to format.
        verbosity: Output detail level ("quiet", "normal", "verbose").

    Returns:
        Formatted string for terminal output.
    """
    status = "PASSED" if report.passed else "FAILED"

    if verbosity == "quiet":
        return f"{report.stage}: {status}"

    lines: list[str] = []
    lines.append(f"Stage: {report.stage} — {status}")
    lines.append("")

    for result in report.results:
        indicator = _result_indicator(result)
        duration = f" ({result.duration_ms}ms)" if result.duration_ms else ""
        lines.append(f"  [{indicator}] {result.name}{duration}")

        if verbosity == "verbose" and result.output:
            lines.extend(
                f"    > {output_line}"
                for output_line in result.output.strip().split("\n")
            )

        lines.extend(f"    {_format_violation(v)}" for v in result.violations)

    lines.append("")
    passed = sum(1 for r in report.results if r.passed)
    total = len(report.results)
    failed = total - passed
    lines.append(f"{passed}/{total} checks passed, {failed} failed")

    if report.duration_ms:
        lines.append(f"Total time: {report.duration_ms}ms")

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
# R2: Gate format
# ---------------------------------------------------------------------------


def format_gate(report: Any) -> tuple[str, int]:
    """Format a CheckReport for Git Hook gate output.

    Args:
        report: Any to format.

    Returns:
        Tuple of (message, exit_code).
    """
    if report.passed:
        return f"ai-guard: {report.stage} checks passed", 0

    failed_names = [r.name for r in report.results if not r.passed]
    msg = f"ai-guard: {report.stage} checks failed: {', '.join(failed_names)}"
    return msg, 1


# ---------------------------------------------------------------------------
# Markdown format
# ---------------------------------------------------------------------------


def format_markdown(
    report: Any,
    locale: str = "en",
) -> str:
    """Format a CheckReport as Markdown using Jinja2 templates.

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
