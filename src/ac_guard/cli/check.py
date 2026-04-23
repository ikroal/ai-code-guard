"""check, verify, run, and gate command implementations for AI Code Guard CLI.

Provides CLI entry points for code quality checking, delegating to
the Checker module for execution and Reporter for output formatting.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ac_guard.checker.core import (
    BUCKET_AWARE_STAGES,
    StageOptions,
    get_changed_files,
    run_check,
    run_precommit,
    run_stage,
)
from ac_guard.config import ConfigError, resolve_config
from ac_guard.domain.models import CheckResult, StageOutcome
from ac_guard.reporter import (
    FormatKind,
    GitPlatformCfg,
    ReportConfig,
    TerminalCfg,
    report,
)

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

    outcome = run_stage(
        "pre-commit",
        resolved.code,
        project_root,
        options=StageOptions(
            files=file_list,
            languages=list(resolved.languages),
        ),
    )

    _report_to_terminal(outcome, output_format, resolved.output.locale)
    _maybe_post_pr(outcome, resolved.output.pr_report, resolved.output.locale)
    raise SystemExit(0 if outcome.passed else 1)


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

    outcome = run_stage(
        "pre-push",
        resolved.code,
        project_root,
        options=StageOptions(
            build_command=build_cmd,
            languages=list(resolved.languages),
        ),
    )

    _report_to_terminal(outcome, output_format, resolved.output.locale)
    _maybe_post_pr(outcome, resolved.output.pr_report, resolved.output.locale)
    raise SystemExit(0 if outcome.passed else 1)


def run_command(
    name: str,
    stage: str,
    files: list[str],
    config_path: Path,
) -> None:
    """Execute the run command (single check item).

    Args:
        name: Check name to run.
        stage: Check stage ("pre-commit" or "pre-push").
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
        # Search custom checks across every gating stage bucket. A check
        # ID is unique across the config; first hit wins.
        check_item = None
        for _stage_name, bucket in resolved.code.buckets():
            if name in bucket.checks:
                check_item = bucket.checks[name]
                break
        if check_item is None:
            print(f"Error: Check '{name}' not found.")
            available = [
                check_name
                for _stage_name, bucket in resolved.code.buckets()
                for check_name in bucket.checks
            ]
            if available:
                print(f"Available checks: {', '.join(available)}")
            raise SystemExit(1)
        results.append(run_check(name, check_item, file_list, project_root))

    passed = all(r.passed for r in results)
    duration = sum(r.duration_ms for r in results)
    outcome = StageOutcome(
        stage=stage,
        passed=passed,
        results=results,
        duration_ms=duration,
    )

    _report_to_terminal(outcome, "text", resolved.output.locale)
    raise SystemExit(0 if outcome.passed else 1)


_GATING_STAGES = frozenset(
    {"pre-commit", "commit-msg", "pre-merge-commit", "pre-push", "pre-rebase"}
)


def gate_run_command(
    stage: str,
    config_path: Path,
    *,
    argv: list[str] | None = None,
) -> None:
    """Execute the gate run command (Git Hook entry).

    Args:
        stage: One of the five pre-commit gating stages
            (``pre-commit`` / ``commit-msg`` / ``pre-merge-commit`` /
            ``pre-push`` / ``pre-rebase``). Schema-v1 values
            (``commit`` / ``push``) are rejected.
        config_path: Path to guard.yaml.
        argv: Pass-through positional args (e.g. commit-msg hook
            receives the message file path as $1).
    """
    if stage not in _GATING_STAGES:
        print(
            f"Error: unknown stage '{stage}'. Expected one of "
            f"{sorted(_GATING_STAGES)}.",
            flush=True,
        )
        raise SystemExit(2)

    resolved = _load_config(config_path)
    project_root = config_path.parent.resolve()

    if stage in BUCKET_AWARE_STAGES:
        build_cmd = resolved.build_command if stage == "pre-push" else None
        outcome = run_stage(
            stage,
            resolved.code,
            project_root,
            options=StageOptions(
                build_command=build_cmd,
                languages=list(resolved.languages),
            ),
        )
        _report_to_terminal(outcome, "text", resolved.output.locale)
        _maybe_post_pr(outcome, resolved.output.pr_report, resolved.output.locale)
        raise SystemExit(0 if outcome.passed else 1)

    # commit-msg / pre-merge-commit / pre-rebase — ac-guard doesn't
    # yet model these in its bucket-aware checker. Delegate to
    # pre-commit's native stage runner; it reads the generated
    # .pre-commit-config.yaml and executes hooks declared for this
    # stage via their ``stages:`` field.
    import subprocess

    cmd = ["pre-commit", "run", "--hook-stage", stage]
    if stage == "commit-msg" and argv:
        cmd.extend(["--commit-msg-filename", argv[0]])
    else:
        cmd.append("--all-files")
    result = subprocess.run(cmd, cwd=project_root, check=False)
    raise SystemExit(result.returncode)


def _report_to_terminal(outcome: StageOutcome, output_format: str, locale: str) -> None:
    """Dispatch ``outcome`` to stdout via the reporter.

    Args:
        outcome: The check outcome.
        output_format: ``"text"`` or ``"json"``.
        locale: Label locale for text rendering (ignored for JSON).
    """
    fmt = FormatKind.JSON if output_format == "json" else FormatKind.TEXT
    report(
        outcome,
        ReportConfig(channel=TerminalCfg(), format=fmt, locale=locale),
    )


def _maybe_post_pr(outcome: StageOutcome, pr_report, locale: str) -> None:
    """Post the outcome to the configured Git platform if enabled.

    Short-circuits when ``pr_report.enabled`` is ``False``. Otherwise
    dispatches via :func:`reporter.report` with ``non_blocking=True`` so
    HTTP/auth failures never affect the caller's exit code.
    """
    if not pr_report.enabled:
        return
    report(
        outcome,
        ReportConfig(
            channel=GitPlatformCfg(
                platform=pr_report.platform,
                token_env=pr_report.token_env,
                api_url=pr_report.api_url,
            ),
            format=FormatKind.MARKDOWN,
            locale=locale,
        ),
        non_blocking=True,
    )


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
