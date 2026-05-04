"""Unified ``ac-guard run`` command implementation.

Thin rendering layer over ``ac_guard.code_gate``:

- Positional ``<name>`` present → single-check path (``gate_check``);
  no PR comment side effect.
- ``<name>`` absent → full-stage path (``gate_stage``); posts PR
  comment when configured.

Both modes share argument parsing, config loading, and reporter
plumbing. Side effects are determined by **scope** (single check vs
full stage), not by command name.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ac_guard.code_gate import GateOptions, gate_check, gate_stage
from ac_guard.config import ConfigError, resolve_config
from ac_guard.reporter import (
    FormatKind,
    GitPlatformCfg,
    ReportConfig,
    TerminalCfg,
    report,
)

if TYPE_CHECKING:
    from pathlib import Path

    from ac_guard.domain.models import StageOutcome

__all__ = ["RunRequest", "run_command"]


@dataclass(frozen=True)
class RunRequest:
    """Bundle of inputs that drive a single ``ac-guard run`` invocation.

    Bundling keeps :func:`run_command` within the project's argument-count
    limits and makes the dispatch criteria (``name`` present? what stage?)
    explicit at call sites.

    Attributes:
        name: Check name to run, or ``None`` for full-stage mode.
        stage: Stage selector. In full-stage mode this is the gating
            stage to run; in single-check mode this is a hint that
            drives file collection.
        files: Explicit file list (empty for auto-detect).
        config_path: Path to guard.yaml.
        skip_build: Suppress the build step (only meaningful when
            ``stage == "pre-push"`` in full-stage mode).
        output_format: ``"text"`` or ``"json"``.
        argv: Stage-specific positional args forwarded by git hooks
            (commit-msg uses it for the message file path). Only
            consumed in full-stage mode.
    """

    name: str | None
    stage: str
    files: list[str]
    config_path: Path
    skip_build: bool = False
    output_format: str = "text"
    argv: list[str] | None = None


def run_command(request: RunRequest) -> None:
    """Run quality checks (single check by name, or full stage via stage).

    Dispatches to :func:`gate_check` or :func:`gate_stage` based on
    whether ``request.name`` is set, and renders the resulting
    ``StageOutcome`` via the reporter. Always raises ``SystemExit``.
    """
    resolved = _load_config(request.config_path)
    project_root = request.config_path.parent.resolve()

    if request.name is None:
        outcome = _run_full_stage(request, resolved, project_root)
        _report_to_terminal(outcome, request.output_format, resolved.output.locale)
        _maybe_post_pr(outcome, resolved.output.pr_report, resolved.output.locale)
    else:
        outcome = _run_single_check(request, resolved, project_root)
        _report_to_terminal(outcome, request.output_format, resolved.output.locale)

    raise SystemExit(0 if outcome.passed else 1)


def _run_full_stage(request: RunRequest, resolved, project_root: Path) -> StageOutcome:
    """Dispatch to ``gate_stage``, mapping ``ValueError`` to exit 2."""
    build_command = (
        None
        if request.skip_build or request.stage != "pre-push"
        else resolved.build_command
    )
    try:
        return gate_stage(
            request.stage,
            resolved.code,
            project_root,
            options=GateOptions(
                argv=request.argv,
                build_command=build_command,
                files=request.files or None,
                languages=list(resolved.languages),
            ),
        )
    except ValueError as e:
        print(f"Error: {e}", flush=True)
        raise SystemExit(2) from None


def _run_single_check(
    request: RunRequest, resolved, project_root: Path
) -> StageOutcome:
    """Dispatch to ``gate_check``, mapping ``KeyError`` to exit 1."""
    try:
        return gate_check(
            request.name,
            resolved.code,
            project_root,
            stage_hint=request.stage,
            options=GateOptions(
                files=request.files or None,
                languages=list(resolved.languages),
            ),
        )
    except KeyError as e:
        message = e.args[0] if e.args else str(e)
        print(f"Error: {message}")
        raise SystemExit(1) from None


def _report_to_terminal(outcome: StageOutcome, output_format: str, locale: str) -> None:
    """Dispatch ``outcome`` to stdout via the reporter."""
    fmt = FormatKind.JSON if output_format == "json" else FormatKind.TEXT
    report(
        outcome,
        ReportConfig(channel=TerminalCfg(), format=fmt, locale=locale),
    )


def _maybe_post_pr(outcome: StageOutcome, pr_report, locale: str) -> None:
    """Post the outcome to the configured Git platform if enabled."""
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
    """Load and resolve config, handling errors."""
    try:
        return resolve_config(config_path)
    except ConfigError as e:
        print(f"Error: {e}")
        raise SystemExit(1) from None
