"""Code gate core — orchestration over git lifecycle moments.

Public API:
    gate_stage(stage, config, project_root, *, options) -> StageOutcome
        Run all checks configured for a git lifecycle moment.
    gate_check(name, config, project_root, *, options) -> StageOutcome
        Run a single named check (built-in shortcut or custom check).
    is_modeled_stage(stage) -> bool
        Whether ac-guard models the stage with a bucket-aware bucket
        (vs. delegating to the underlying managed framework).
    GateOptions
        Optional refinements: explicit file list, language identifiers,
        build command override.

Internal layering:
    Per-stage runtime processing is encapsulated in private strategy
    objects (``_CommitStrategy`` / ``_PushStrategy`` / ``_DelegatedStrategy``)
    behind the ``_StageStrategy`` Protocol. ``gate_stage`` is a one-line
    dispatch into the strategy registry. Two execution backends sit
    underneath: ``_run_managed_hook`` (single hook through the managed
    framework) and ``_run_command`` (literal subprocess); a third
    private path (``_delegate_managed_stage``) hands an entire stage
    off to the managed framework for non-modeled stages.

Errors:
    ``gate_stage`` raises ``ValueError`` for unknown stage names.
    ``gate_check`` raises ``KeyError`` (with available names listed)
    when ``name`` is neither a built-in shortcut nor present in any
    bucket. Callers (CLI / git hook scripts) decide how to render.
"""

from __future__ import annotations

import shlex
import shutil
import subprocess
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from ac_guard.domain.languages import TYPE_EXTENSIONS
from ac_guard.domain.models import CheckResult, StageOutcome

if TYPE_CHECKING:
    from pathlib import Path

    from ac_guard.config import CheckItem, CodeConfig, StageBucket

__all__ = [
    "GateOptions",
    "gate_check",
    "gate_stage",
    "is_modeled_stage",
]


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GateOptions:
    """Optional refinements for :func:`gate_stage` and :func:`gate_check`.

    Attributes:
        argv: Stage-specific positional args forwarded by git hooks
            (today only ``commit-msg`` uses it — git passes the
            commit-message file path as ``$1``). Ignored for stages
            ac-guard bucket-models.
        build_command: Shell command for the build check (only used by
            ``gate_stage("pre-push", ...)``). ``None`` disables the build.
        files: Explicit file list. ``None`` means auto-detect via git.
        languages: Language identifiers used to expand ``format-<lang>``
            and ``lint-<lang>`` hook IDs. ``None`` or empty means
            format/lint shortcuts are silently skipped.
    """

    argv: list[str] | None = None
    build_command: str | None = None
    files: list[str] | None = None
    languages: list[str] | None = None


_DEFAULT_OPTIONS = GateOptions()


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


_BUILTIN_CHECKS: frozenset[str] = frozenset({"format", "naming", "lint"})
_NAMING_NOT_IMPLEMENTED_MSG = (
    "Naming check is not yet implemented — tracked in "
    "https://github.com/ikroal/ai-code-guard/issues/95"
)
_BUILD_FAILED_SKIP_REASON = "Skipped: build failed"


# ---------------------------------------------------------------------------
# Stage strategies (private)
# ---------------------------------------------------------------------------


class _StageStrategy(Protocol):
    """Per-stage runtime orchestration. Internal to code_gate."""

    stage: str
    is_modeled: bool

    def run(
        self,
        config: CodeConfig,
        project_root: Path,
        options: GateOptions,
    ) -> StageOutcome: ...


class _CommitStrategy:
    """pre-commit stage: format → lint → custom checks."""

    stage = "pre-commit"
    is_modeled = True

    def run(
        self,
        config: CodeConfig,
        project_root: Path,
        options: GateOptions,
    ) -> StageOutcome:
        start = time.monotonic()
        files = options.files
        if files is None:
            files = _get_changed_files(self.stage, project_root)
        languages = list(options.languages or [])
        results = _run_format_lint_checks(
            config.pre_commit, files, project_root, languages
        )
        return _wrap_outcome(self.stage, results, start)


class _PushStrategy:
    """pre-push stage: pre-commit fail-fast → build → lint → custom checks."""

    stage = "pre-push"
    is_modeled = True

    def __init__(self, commit_strategy: _CommitStrategy) -> None:
        self._commit = commit_strategy

    def run(
        self,
        config: CodeConfig,
        project_root: Path,
        options: GateOptions,
    ) -> StageOutcome:
        start = time.monotonic()
        languages = list(options.languages or [])

        # Phase 1: pre-commit fail-fast
        commit_outcome = self._commit.run(
            config,
            project_root,
            GateOptions(files=options.files, languages=languages),
        )
        if not commit_outcome.passed:
            elapsed = int((time.monotonic() - start) * 1000)
            return StageOutcome(
                stage=self.stage,
                passed=False,
                results=commit_outcome.results,
                duration_ms=elapsed,
            )

        # Phase 2: build → lint → custom checks
        files = options.files
        if files is None:
            files = _get_changed_files(self.stage, project_root)
        results = _run_push_checks(
            config.pre_push, files, project_root, options.build_command, languages
        )
        return _wrap_outcome(self.stage, results, start)


class _DelegatedStrategy:
    """commit-msg / pre-merge-commit / pre-rebase: delegate to managed framework."""

    is_modeled = False

    def __init__(self, stage: str) -> None:
        self.stage = stage

    def run(
        self,
        config: CodeConfig,
        project_root: Path,
        options: GateOptions,
    ) -> StageOutcome:
        del config  # required by Protocol; delegated path doesn't read it
        start = time.monotonic()
        rc = _delegate_managed_stage(self.stage, project_root, argv=options.argv)
        elapsed = int((time.monotonic() - start) * 1000)
        return StageOutcome(
            stage=self.stage,
            passed=rc == 0,
            results=[],
            duration_ms=elapsed,
        )


# Module-private dispatch table
_commit_strategy = _CommitStrategy()
_STRATEGIES: dict[str, _StageStrategy] = {
    "pre-commit": _commit_strategy,
    "pre-push": _PushStrategy(_commit_strategy),
    "commit-msg": _DelegatedStrategy("commit-msg"),
    "pre-merge-commit": _DelegatedStrategy("pre-merge-commit"),
    "pre-rebase": _DelegatedStrategy("pre-rebase"),
}


def _get_strategy(stage: str) -> _StageStrategy:
    """Internal dispatch helper. Raises ValueError for unknown stages."""
    if stage not in _STRATEGIES:
        raise ValueError(
            f"Unknown stage: {stage!r}. Expected one of {sorted(_STRATEGIES)}."
        )
    return _STRATEGIES[stage]


# ---------------------------------------------------------------------------
# Public entrypoints
# ---------------------------------------------------------------------------


def is_modeled_stage(stage: str) -> bool:
    """Return whether ``stage`` is a bucket-aware ac-guard stage.

    Bucket-aware stages (``pre-commit`` / ``pre-push``) run through
    ac-guard's own format/lint/check/build orchestration. Other gating
    stages delegate to the underlying managed framework. Unknown stages
    return ``False`` (total over all string inputs; doctor relies on
    this for safe iteration).
    """
    strategy = _STRATEGIES.get(stage)
    return strategy is not None and strategy.is_modeled


def gate_stage(
    stage: str,
    config: CodeConfig,
    project_root: Path,
    *,
    options: GateOptions = _DEFAULT_OPTIONS,
) -> StageOutcome:
    """Run all checks configured for a git lifecycle moment.

    Dispatches to the per-stage strategy. Bucket-aware stages
    (``pre-commit`` / ``pre-push``) run ac-guard's format/lint/check/build
    orchestration; other gating stages delegate to the underlying managed
    framework.

    Args:
        stage: One of ``pre-commit`` / ``commit-msg`` / ``pre-merge-commit``
            / ``pre-push`` / ``pre-rebase``.
        config: Code configuration tree with per-stage buckets.
        project_root: Path to project root directory.
        options: Optional refinements (file list, languages, build command).

    Returns:
        ``StageOutcome`` aggregating per-check results.

    Raises:
        ValueError: ``stage`` is not a known gating stage.
    """
    return _get_strategy(stage).run(config, project_root, options)


def gate_check(
    name: str,
    config: CodeConfig,
    project_root: Path,
    *,
    stage_hint: str = "pre-commit",
    options: GateOptions = _DEFAULT_OPTIONS,
) -> StageOutcome:
    """Run a single named check (built-in shortcut or custom check).

    Resolution order:
        1. Built-in shortcuts: ``format`` / ``lint`` / ``naming``.
            ``format`` and ``lint`` expand to per-language managed-hook
            calls (``format-<lang>`` / ``lint-<lang>``) using
            ``options.languages``. ``naming`` returns a single skipped
            placeholder result (issue #95).
        2. Custom checks: searches ``config.buckets()`` and runs the
            first match as a literal command.

    Args:
        name: Check name (built-in or custom).
        config: Code configuration tree.
        project_root: Project root directory.
        stage_hint: Stage to drive file collection when
            ``options.files`` is ``None``. ``pre-commit`` uses the
            staged diff; everything else uses ``origin/main..HEAD``.
        options: Optional refinements (file list, languages).

    Returns:
        ``StageOutcome`` with ``stage="ad-hoc:<name>"``. Built-in
        shortcuts may yield multiple per-language results.

    Raises:
        KeyError: ``name`` is neither a built-in shortcut nor a custom
            check in any bucket. The message includes the available
            check names so callers can render a useful error.
    """
    start = time.monotonic()
    files = options.files
    if files is None:
        files = _get_changed_files(stage_hint, project_root)

    results = _resolve_named_check(name, config, files, project_root, options)

    elapsed = int((time.monotonic() - start) * 1000)
    return StageOutcome(
        stage=f"ad-hoc:{name}",
        passed=all(r.passed for r in results),
        results=results,
        duration_ms=elapsed,
    )


# ---------------------------------------------------------------------------
# Bucket orchestration helpers (private)
# ---------------------------------------------------------------------------


def _wrap_outcome(stage: str, results: list[CheckResult], start: float) -> StageOutcome:
    """Common helper: aggregate per-check results into a StageOutcome."""
    elapsed = int((time.monotonic() - start) * 1000)
    return StageOutcome(
        stage=stage,
        passed=all(r.passed for r in results),
        results=results,
        duration_ms=elapsed,
    )


def _run_format_lint_checks(
    bucket: StageBucket,
    files: list[str],
    project_root: Path,
    languages: list[str],
) -> list[CheckResult]:
    """Run a bucket: format → lint → custom checks.

    Used by the pre-commit strategy. (pre-push has its own helper because
    it injects build as a precondition and skips format.)
    """
    results: list[CheckResult] = []

    if bucket.format:
        results.extend(
            _run_managed_hook(f"format-{lang}", files, project_root)
            for lang in languages
        )

    if bucket.lint:
        results.extend(
            _run_managed_hook(f"lint-{lang}", files, project_root) for lang in languages
        )

    for name, check_item in bucket.checks.items():
        results.append(_run_check_item(name, check_item, files, project_root))

    return results


def _run_push_checks(
    bucket: StageBucket,
    files: list[str],
    project_root: Path,
    build_command: str | None,
    languages: list[str],
) -> list[CheckResult]:
    """Run pre-push bucket: build → lint → custom (with build fail-fast).

    Note: pre-push deliberately skips ``bucket.format`` — formatting is
    expected to have happened during the pre-commit stage. Any
    ``format: true`` on the pre-push bucket is silently ignored here.
    """
    results: list[CheckResult] = []

    if build_command:
        build_result = _run_build(build_command, project_root)
        results.append(build_result)
        if not build_result.passed:
            _append_skipped_downstream(results, bucket, languages)
            return results

    if bucket.lint:
        results.extend(
            _run_managed_hook(f"lint-{lang}", files, project_root) for lang in languages
        )

    for name, check_item in bucket.checks.items():
        results.append(_run_check_item(name, check_item, files, project_root))

    return results


def _append_skipped_downstream(
    results: list[CheckResult],
    bucket: StageBucket,
    languages: list[str],
) -> None:
    """Mark lint + push.checks as skipped when build has already failed."""
    if bucket.lint:
        results.extend(
            CheckResult(
                name=f"pre-commit:lint-{lang}",
                passed=True,
                skipped=True,
                output=_BUILD_FAILED_SKIP_REASON,
            )
            for lang in languages
        )
    results.extend(
        CheckResult(
            name=name,
            passed=True,
            skipped=True,
            output=_BUILD_FAILED_SKIP_REASON,
        )
        for name in bucket.checks
    )


# ---------------------------------------------------------------------------
# Named-check resolution
# ---------------------------------------------------------------------------


def _resolve_named_check(
    name: str,
    config: CodeConfig,
    files: list[str],
    project_root: Path,
    options: GateOptions,
) -> list[CheckResult]:
    """Resolve ``name`` to one or more results.

    Built-in shortcuts expand by language; custom checks resolve via
    ``config.buckets()``. Raises ``KeyError`` if neither path matches.
    """
    if name == "naming":
        return [
            CheckResult(
                name="naming",
                passed=True,
                skipped=True,
                output=_NAMING_NOT_IMPLEMENTED_MSG,
            )
        ]

    if name in {"format", "lint"}:
        languages = list(options.languages or [])
        if not languages:
            return [
                CheckResult(
                    name=name,
                    passed=True,
                    skipped=True,
                    output="No languages configured",
                )
            ]
        return [
            _run_managed_hook(f"{name}-{lang}", files, project_root)
            for lang in languages
        ]

    for _stage_name, bucket in config.buckets():
        if name in bucket.checks:
            return [_run_check_item(name, bucket.checks[name], files, project_root)]

    available = [
        check_name
        for _stage_name, bucket in config.buckets()
        for check_name in bucket.checks
    ]
    raise KeyError(
        f"Check {name!r} not found."
        + (f" Available checks: {', '.join(available)}." if available else "")
    )


def _run_check_item(
    name: str,
    check_item: CheckItem,
    files: list[str],
    project_root: Path,
) -> CheckResult:
    """Adapt a ``CheckItem`` to ``_run_command``.

    Owns CheckItem-specific concerns: ``enabled`` / ``types`` filtering,
    ``pass_filenames`` substitution, and ``timeout`` selection. Then
    hands a fully-rendered command to the literal-command runner.
    """
    if not check_item.enabled:
        return CheckResult(name=name, passed=True, skipped=True, output="Disabled")

    filtered = _filter_files_by_type(files, check_item.types)
    if check_item.types and not filtered:
        return CheckResult(
            name=name, passed=True, skipped=True, output="No matching files"
        )

    rendered = check_item.command
    if check_item.pass_filenames and filtered:
        if "{files}" in rendered:
            rendered = rendered.replace("{files}", " ".join(filtered))
        else:
            rendered = f"{rendered} {' '.join(filtered)}"

    return _run_command(name, rendered, project_root, timeout=check_item.timeout)


def _run_build(command: str, project_root: Path) -> CheckResult:
    """Run the build command (literal shell, 600s timeout, fixed name)."""
    return _run_command("build", command, project_root, timeout=600)


# ---------------------------------------------------------------------------
# Execution backends (private)
# ---------------------------------------------------------------------------


def _run_managed_hook(
    hook_id: str,
    files: list[str],
    project_root: Path,
) -> CheckResult:
    """Run a single declarative hook through the managed framework.

    Today this calls the ``pre-commit`` Python framework. The function
    name intentionally hides that — swapping the underlying runner
    (Lefthook, custom runner) only touches this body.
    """
    name = f"pre-commit:{hook_id}"

    if not shutil.which("pre-commit"):
        return CheckResult(
            name=name,
            passed=True,
            skipped=True,
            output="pre-commit not installed",
        )

    if not files:
        return CheckResult(
            name=name,
            passed=True,
            skipped=True,
            output="No files to check",
        )

    cmd = ["pre-commit", "run", hook_id, "--files", *files]
    start = time.monotonic()

    try:
        result = subprocess.run(
            cmd,
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        elapsed = int((time.monotonic() - start) * 1000)
        return CheckResult(
            name=name,
            passed=result.returncode == 0,
            duration_ms=elapsed,
            output=result.stdout + result.stderr,
        )
    except subprocess.TimeoutExpired:
        elapsed = int((time.monotonic() - start) * 1000)
        return CheckResult(
            name=name,
            passed=False,
            duration_ms=elapsed,
            output="Timed out after 120s",
        )
    except OSError as e:
        return CheckResult(
            name=name,
            passed=False,
            output=str(e),
        )


def _run_command(
    name: str,
    command: str,
    project_root: Path,
    *,
    timeout: int,
) -> CheckResult:
    """Run a literal shell command and capture its result.

    Pure subprocess wrapper: command construction (file substitution,
    type filtering, etc.) is the caller's responsibility. Used by
    ``_run_check_item`` (after rendering CheckItem fields) and
    ``_run_build``.
    """
    start = time.monotonic()

    try:
        result = subprocess.run(
            shlex.split(command),
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        elapsed = int((time.monotonic() - start) * 1000)
        return CheckResult(
            name=name,
            passed=result.returncode == 0,
            duration_ms=elapsed,
            output=result.stdout + result.stderr,
        )
    except subprocess.TimeoutExpired:
        elapsed = int((time.monotonic() - start) * 1000)
        return CheckResult(
            name=name,
            passed=False,
            duration_ms=elapsed,
            output=f"Timed out after {timeout}s",
        )
    except OSError as e:
        return CheckResult(
            name=name,
            passed=False,
            output=str(e),
        )


def _delegate_managed_stage(
    stage: str,
    project_root: Path,
    *,
    argv: list[str] | None = None,
) -> int:
    """Delegate an entire git stage to the managed framework.

    Used for stages ac-guard does not bucket-model (``commit-msg``,
    ``pre-merge-commit``, ``pre-rebase``). Streams pre-commit's native
    output (stdout/stderr not captured) and returns its exit code.

    For ``commit-msg``, the first ``argv`` entry (the message file path
    that git passes as ``$1``) is forwarded as
    ``--commit-msg-filename``. Other stages always use ``--all-files``.
    """
    cmd = ["pre-commit", "run", "--hook-stage", stage]
    if stage == "commit-msg" and argv:
        cmd.extend(["--commit-msg-filename", argv[0]])
    else:
        cmd.append("--all-files")
    result = subprocess.run(cmd, cwd=project_root, check=False)
    return result.returncode


# ---------------------------------------------------------------------------
# File collection (private)
# ---------------------------------------------------------------------------


def _get_changed_files(stage: str, project_root: Path) -> list[str]:
    """Return staged or push-range changed files via git."""
    if stage == "pre-commit":
        cmd = ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"]
    else:
        cmd = ["git", "diff", "origin/main..HEAD", "--name-only", "--diff-filter=ACMR"]

    try:
        result = subprocess.run(
            cmd,
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if result.returncode != 0:
            return []
        return [f for f in result.stdout.strip().split("\n") if f]
    except (subprocess.TimeoutExpired, OSError):
        return []


def _filter_files_by_type(files: list[str], types: list[str] | None) -> list[str]:
    """Filter ``files`` by file-type extensions (e.g. ``["python"]``)."""
    if types is None:
        return files

    valid_exts: set[str] = set()
    for t in types:
        valid_exts.update(TYPE_EXTENSIONS.get(t, frozenset({f".{t}"})))

    return [f for f in files if any(f.endswith(ext) for ext in valid_exts)]
