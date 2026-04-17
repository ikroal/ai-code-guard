"""check, verify, run, and gate command implementations for AI Code Guard CLI.

Provides CLI entry points for code quality checking, delegating to
the Checker module for execution and Reporter for output formatting.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ac_guard.checker.core import (
    get_changed_files,
    run_check,
    run_precommit,
    run_stage,
)
from ac_guard.checker.models import CheckReport, CheckResult
from ac_guard.config.exceptions import ConfigError
from ac_guard.config.merger import resolve_config
from ac_guard.reporter.formatting import format_gate, format_json, format_terminal

if TYPE_CHECKING:
    from pathlib import Path

__all__ = [
    "check_command",
    "gate_run_command",
    "run_command",
    "verify_command",
]

_BUILTIN_CHECKS = frozenset({"format", "naming", "lint"})
_NAMING_NOT_IMPLEMENTED_MSG = (
    "Naming check is not yet implemented — tracked in "
    "https://github.com/ikroal/ai-code-guard/issues/95"
)


def check_command(
    files: list[str],
    config_path: Path,
    *,
    output_format: str = "text",
) -> None:
    """Execute the check command (commit-stage checks).

    Args:
        files: Explicit file list, or empty for auto-detect.
        config_path: Path to guard.yaml.
        output_format: Output format (``"text"`` or ``"json"``).
    """
    resolved = _load_config(config_path)
    project_root = config_path.parent.resolve()
    file_list = files or None

    report = run_stage(
        "commit",
        resolved.code,
        project_root,
        files=file_list,
        languages=list(resolved.languages),
    )

    print(
        _format_report(
            report,
            output_format,
            resolved.output.verbosity,
            resolved.output.locale,
        )
    )
    raise SystemExit(0 if report.passed else 1)


def verify_command(
    skip_build: bool,
    config_path: Path,
    *,
    output_format: str = "text",
) -> None:
    """Execute the verify command (push-stage validation).

    Args:
        skip_build: Whether to skip the build step.
        config_path: Path to guard.yaml.
        output_format: Output format (``"text"`` or ``"json"``).
    """
    resolved = _load_config(config_path)
    project_root = config_path.parent.resolve()
    build_cmd = None if skip_build else resolved.build_command

    report = run_stage(
        "push",
        resolved.code,
        project_root,
        build_command=build_cmd,
        languages=list(resolved.languages),
    )

    print(
        _format_report(
            report,
            output_format,
            resolved.output.verbosity,
            resolved.output.locale,
        )
    )
    raise SystemExit(0 if report.passed else 1)


def run_command(
    name: str,
    stage: str,
    files: list[str],
    config_path: Path,
) -> None:
    """Execute the run command (single check item).

    Args:
        name: Check name to run.
        stage: Check stage ("commit" or "push").
        files: Explicit file list, or empty for auto-detect.
        config_path: Path to guard.yaml.
    """
    resolved = _load_config(config_path)
    project_root = config_path.parent.resolve()
    file_list = files or get_changed_files(stage, project_root)

    # Built-in pre-commit shortcuts (format / naming / lint)
    results: list = []
    if name in _BUILTIN_CHECKS:
        if name == "naming":
            results.append(
                CheckResult(
                    name="naming",
                    passed=True,
                    skipped=True,
                    output=_NAMING_NOT_IMPLEMENTED_MSG,
                )
            )
        else:  # format or lint — iterate languages
            results.extend(
                run_precommit(f"{name}-{lang}", file_list, project_root)
                for lang in resolved.languages
            )
            if not results:
                # No languages configured — nothing to run
                results.append(
                    CheckResult(
                        name=name,
                        passed=True,
                        skipped=True,
                        output="No languages configured",
                    )
                )
    else:
        # Search custom checks in both stages
        check_item = resolved.code.commit_checks.get(name)
        if check_item is None:
            check_item = resolved.code.push_checks.get(name)
        if check_item is None:
            print(f"Error: Check '{name}' not found in {stage} stage.")
            available = list(resolved.code.commit_checks) + list(
                resolved.code.push_checks
            )
            if available:
                print(f"Available checks: {', '.join(available)}")
            raise SystemExit(1)
        results.append(run_check(name, check_item, file_list, project_root))

    passed = all(r.passed for r in results)
    duration = sum(r.duration_ms for r in results)
    report = CheckReport(
        stage=stage,
        passed=passed,
        results=results,
        duration_ms=duration,
    )

    print(
        _format_report(
            report, "text", resolved.output.verbosity, resolved.output.locale
        )
    )
    raise SystemExit(0 if report.passed else 1)


def gate_run_command(
    stage: str,
    config_path: Path,
) -> None:
    """Execute the gate run command (Git Hook entry).

    Args:
        stage: Check stage ("commit" or "push").
        config_path: Path to guard.yaml.
    """
    resolved = _load_config(config_path)
    project_root = config_path.parent.resolve()
    build_cmd = resolved.build_command if stage == "push" else None

    report = run_stage(
        stage,
        resolved.code,
        project_root,
        build_command=build_cmd,
        languages=list(resolved.languages),
    )

    message, exit_code = format_gate(report)
    print(message)
    raise SystemExit(exit_code)


def _format_report(
    report: CheckReport,
    output_format: str,
    verbosity: str,
    locale: str = "en",
) -> str:
    """Format a CheckReport for output.

    Args:
        report: The check report to format.
        output_format: ``"text"`` or ``"json"``.
        verbosity: Verbosity level for text output.
        locale: Label locale for terminal output (``"en"`` or
            ``"zh-CN"``). Ignored for JSON.

    Returns:
        Formatted string.
    """
    if output_format == "json":
        return format_json(report)
    return format_terminal(report, verbosity=verbosity, locale=locale)


def _load_config(config_path: Path):
    """Load and resolve config, handling errors.

    Args:
        config_path: Path to guard.yaml.

    Returns:
        ResolvedConfig.
    """
    try:
        return resolve_config(config_path)
    except ConfigError as e:
        print(f"Error: {e}")
        raise SystemExit(1) from None
