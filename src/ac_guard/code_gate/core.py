"""Code gate core — check orchestration primitives (K2-K6).

Orchestrates code quality checks across commit and push stages
by delegating to pre-commit framework and custom check commands.
"""

from __future__ import annotations

import shlex
import shutil
import subprocess
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ac_guard.domain.languages import TYPE_EXTENSIONS
from ac_guard.domain.models import CheckResult, StageOutcome

if TYPE_CHECKING:
    from pathlib import Path

    from ac_guard.config import CheckItem, CodeConfig

__all__ = [
    "BUCKET_AWARE_STAGES",
    "StageOptions",
    "get_changed_files",
    "run_build",
    "run_check",
    "run_precommit",
    "run_stage",
]


@dataclass(frozen=True)
class StageOptions:
    """Optional refinements for :func:`run_stage`.

    Keeps the primary orchestration signature short while still allowing
    callers to override the file list, language set, or build command
    used by a stage run.

    Attributes:
        build_command: Shell command to execute for the build check
            (``pre-push`` stage only). ``None`` disables the build.
        files: Explicit file list. ``None`` means auto-detect via git.
        languages: Language identifiers used to resolve pre-commit hook
            IDs (``format-<lang>`` / ``lint-<lang>``). ``None`` or empty
            means format/lint shortcuts are silently skipped.
    """

    build_command: str | None = None
    files: list[str] | None = None
    languages: list[str] | None = None


_DEFAULT_STAGE_OPTIONS = StageOptions()


# Stages where ac-guard provides bucket-aware orchestration (format/lint
# shortcuts, build command, StageOutcome for reporter/audit). Other gating
# stages delegate to ``pre-commit run --hook-stage`` via cli/check.py.
BUCKET_AWARE_STAGES: frozenset[str] = frozenset({"pre-commit", "pre-push"})


# ---------------------------------------------------------------------------
# K2: Get changed files
# ---------------------------------------------------------------------------


def get_changed_files(stage: str, project_root: Path) -> list[str]:
    """Get list of changed files for the given stage.

    Args:
        stage: Check stage ("pre-commit" or "pre-push").
        project_root: Path to project root directory.

    Returns:
        List of changed file paths relative to project root.
    """
    if stage == "pre-commit":
        cmd = ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"]
    else:
        # pre-push stage: diff against upstream
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


# ---------------------------------------------------------------------------
# K3: Run pre-commit
# ---------------------------------------------------------------------------


def run_precommit(
    hook_id: str,
    files: list[str],
    project_root: Path,
) -> CheckResult:
    """Run a pre-commit hook by ID.

    Args:
        hook_id: Pre-commit hook identifier (e.g., "ruff").
        files: List of files to check.
        project_root: Path to project root directory.

    Returns:
        CheckResult for the pre-commit hook run.
    """
    if not shutil.which("pre-commit"):
        return CheckResult(
            name=f"pre-commit:{hook_id}",
            passed=True,
            skipped=True,
            output="pre-commit not installed",
        )

    if not files:
        return CheckResult(
            name=f"pre-commit:{hook_id}",
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
            name=f"pre-commit:{hook_id}",
            passed=result.returncode == 0,
            duration_ms=elapsed,
            output=result.stdout + result.stderr,
        )
    except subprocess.TimeoutExpired:
        elapsed = int((time.monotonic() - start) * 1000)
        return CheckResult(
            name=f"pre-commit:{hook_id}",
            passed=False,
            duration_ms=elapsed,
            output="Timed out after 120s",
        )
    except OSError as e:
        return CheckResult(
            name=f"pre-commit:{hook_id}",
            passed=False,
            output=str(e),
        )


# ---------------------------------------------------------------------------
# K4: Run custom check command
# ---------------------------------------------------------------------------


def run_check(
    check_name: str,
    check_item: CheckItem,
    files: list[str],
    project_root: Path,
) -> CheckResult:
    """Execute a custom check command.

    Args:
        check_name: Check identifier.
        check_item: CheckItem with command, timeout, types.
        files: List of changed files.
        project_root: Path to project root directory.

    Returns:
        CheckResult for the command execution.
    """
    if not check_item.enabled:
        return CheckResult(
            name=check_name, passed=True, skipped=True, output="Disabled"
        )

    # Filter files by type if specified
    filtered = _filter_files_by_type(files, check_item.types)
    if check_item.types and not filtered:
        return CheckResult(
            name=check_name,
            passed=True,
            skipped=True,
            output="No matching files",
        )

    # Build command
    command = check_item.command
    if check_item.pass_filenames and filtered:
        if "{files}" in command:
            command = command.replace("{files}", " ".join(filtered))
        else:
            command = f"{command} {' '.join(filtered)}"

    start = time.monotonic()

    try:
        result = subprocess.run(
            shlex.split(command),
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=check_item.timeout,
            check=False,
        )
        elapsed = int((time.monotonic() - start) * 1000)
        return CheckResult(
            name=check_name,
            passed=result.returncode == 0,
            duration_ms=elapsed,
            output=result.stdout + result.stderr,
        )
    except subprocess.TimeoutExpired:
        elapsed = int((time.monotonic() - start) * 1000)
        return CheckResult(
            name=check_name,
            passed=False,
            duration_ms=elapsed,
            output=f"Timed out after {check_item.timeout}s",
        )
    except OSError as e:
        return CheckResult(
            name=check_name,
            passed=False,
            output=str(e),
        )


def _filter_files_by_type(files: list[str], types: list[str] | None) -> list[str]:
    """Filter file list by type extensions.

    Args:
        files: List of file paths.
        types: File type names (e.g., ["python", "typescript"]).
            None means no filtering.

    Returns:
        Filtered file list.
    """
    if types is None:
        return files

    valid_exts: set[str] = set()
    for t in types:
        valid_exts.update(TYPE_EXTENSIONS.get(t, frozenset({f".{t}"})))

    return [f for f in files if any(f.endswith(ext) for ext in valid_exts)]


# ---------------------------------------------------------------------------
# K5: Run build
# ---------------------------------------------------------------------------


def run_build(build_command: str, project_root: Path) -> CheckResult:
    """Execute the build command.

    Args:
        build_command: Shell command to run.
        project_root: Path to project root directory.

    Returns:
        CheckResult for the build execution.
    """
    start = time.monotonic()

    try:
        result = subprocess.run(
            shlex.split(build_command),
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
        elapsed = int((time.monotonic() - start) * 1000)
        return CheckResult(
            name="build",
            passed=result.returncode == 0,
            duration_ms=elapsed,
            output=result.stdout + result.stderr,
        )
    except subprocess.TimeoutExpired:
        elapsed = int((time.monotonic() - start) * 1000)
        return CheckResult(
            name="build",
            passed=False,
            duration_ms=elapsed,
            output="Build timed out after 600s",
        )
    except OSError as e:
        return CheckResult(
            name="build",
            passed=False,
            output=str(e),
        )


# ---------------------------------------------------------------------------
# K6: Run stage (orchestration)
# ---------------------------------------------------------------------------


def run_stage(
    stage: str,
    code_config: CodeConfig,
    project_root: Path,
    *,
    options: StageOptions = _DEFAULT_STAGE_OPTIONS,
) -> StageOutcome:
    """Orchestrate all checks for a stage.

    For pre-commit stage: format + lint + custom checks.
    For pre-push stage: pre-commit first (fail-fast) + build + lint + custom.

    Args:
        stage: Check stage ("pre-commit" or "pre-push").
        code_config: CodeConfig with enabled flags and checks.
        project_root: Path to project root directory.
        options: Optional refinements (build command, explicit file list,
            language identifiers). See :class:`StageOptions`.

    Returns:
        StageOutcome with aggregated results.
    """
    start = time.monotonic()
    langs = list(options.languages or [])

    if stage == "pre-push":
        # Fail-fast: run pre-commit stage first, propagating file/language
        # overrides but suppressing the build command (pre-commit has no build).
        commit_report = run_stage(
            "pre-commit",
            code_config,
            project_root,
            options=StageOptions(files=options.files, languages=langs),
        )
        if not commit_report.passed:
            elapsed = int((time.monotonic() - start) * 1000)
            return StageOutcome(
                stage="pre-push",
                passed=False,
                results=commit_report.results,
                duration_ms=elapsed,
            )

    files = options.files
    if files is None:
        files = get_changed_files(stage, project_root)
    results: list[CheckResult] = []

    if stage == "pre-commit":
        results.extend(_run_commit_checks(code_config, files, project_root, langs))
    else:
        results.extend(
            _run_push_checks(
                code_config, files, project_root, options.build_command, langs
            )
        )

    elapsed = int((time.monotonic() - start) * 1000)
    passed = all(r.passed for r in results)

    return StageOutcome(
        stage=stage,
        passed=passed,
        results=results,
        duration_ms=elapsed,
    )


_BUILD_FAILED_SKIP_REASON = "Skipped: build failed"


def _run_commit_checks(
    config: CodeConfig,
    files: list[str],
    project_root: Path,
    languages: list[str],
) -> list[CheckResult]:
    """Run commit-stage (pre-commit bucket) checks.

    Schema v2 (#123): reads ``config.pre_commit.*`` directly. The dead
    ``naming`` shortcut (D8) is gone — ruff N-rules via ``lint: true``
    replaced it.
    """
    results: list[CheckResult] = []
    bucket = config.pre_commit

    if bucket.format:
        results.extend(
            run_precommit(f"format-{lang}", files, project_root) for lang in languages
        )

    if bucket.lint:
        results.extend(
            run_precommit(f"lint-{lang}", files, project_root) for lang in languages
        )

    for name, check_item in bucket.checks.items():
        results.append(run_check(name, check_item, files, project_root))

    return results


def _run_push_checks(
    config: CodeConfig,
    files: list[str],
    project_root: Path,
    build_command: str | None,
    languages: list[str],
) -> list[CheckResult]:
    """Run push-stage (pre-push bucket) checks.

    Build is a precondition: if it fails, lint and custom push checks
    are not executed and are instead appended as ``skipped`` results
    with a ``Skipped: build failed`` marker.
    """
    results: list[CheckResult] = []
    bucket = config.pre_push

    if build_command:
        build_result = run_build(build_command, project_root)
        results.append(build_result)
        if not build_result.passed:
            _append_skipped_downstream(results, config, languages)
            return results

    if bucket.lint:
        results.extend(
            run_precommit(f"lint-{lang}", files, project_root) for lang in languages
        )

    for name, check_item in bucket.checks.items():
        results.append(run_check(name, check_item, files, project_root))

    return results


def _append_skipped_downstream(
    results: list[CheckResult],
    config: CodeConfig,
    languages: list[str],
) -> None:
    """Mark lint + push.checks as skipped when build has already failed."""
    if config.pre_push.lint:
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
        for name in config.pre_push.checks
    )
