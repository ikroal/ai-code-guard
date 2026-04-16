"""Checker core — check orchestration primitives (K2-K6).

Orchestrates code quality checks across commit and push stages
by delegating to pre-commit framework and custom check commands.
"""

from __future__ import annotations

import shlex
import shutil
import subprocess
import time
from typing import TYPE_CHECKING

from ai_guard.checker.models import CheckReport, CheckResult

if TYPE_CHECKING:
    from pathlib import Path

    from ai_guard.config.models import CheckItem, CodeConfig

__all__ = [
    "get_changed_files",
    "run_build",
    "run_check",
    "run_precommit",
    "run_stage",
]


# ---------------------------------------------------------------------------
# K2: Get changed files
# ---------------------------------------------------------------------------


def get_changed_files(stage: str, project_root: Path) -> list[str]:
    """Get list of changed files for the given stage.

    Args:
        stage: Check stage ("commit" or "push").
        project_root: Path to project root directory.

    Returns:
        List of changed file paths relative to project root.
    """
    if stage == "commit":
        cmd = ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"]
    else:
        # Push stage: diff against upstream
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

    type_extensions = {
        "python": {".py", ".pyi"},
        "javascript": {".js", ".jsx", ".mjs"},
        "typescript": {".ts", ".tsx", ".mts"},
        "go": {".go"},
        "rust": {".rs"},
        "java": {".java"},
        "c": {".c", ".h"},
        "cpp": {".cpp", ".cc", ".cxx", ".hpp", ".hh"},
    }

    valid_exts: set[str] = set()
    for t in types:
        valid_exts.update(type_extensions.get(t, {f".{t}"}))

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
    build_command: str | None = None,
) -> CheckReport:
    """Orchestrate all checks for a stage.

    For commit stage: format + naming + custom checks.
    For push stage: commit first (fail-fast) + build + lint + custom checks.

    Args:
        stage: Check stage ("commit" or "push").
        code_config: CodeConfig with enabled flags and checks.
        project_root: Path to project root directory.
        build_command: Optional build command (push stage only).

    Returns:
        CheckReport with aggregated results.
    """
    start = time.monotonic()

    if stage == "push":
        # Fail-fast: run commit stage first
        commit_report = run_stage("commit", code_config, project_root)
        if not commit_report.passed:
            elapsed = int((time.monotonic() - start) * 1000)
            return CheckReport(
                stage="push",
                passed=False,
                results=commit_report.results,
                duration_ms=elapsed,
            )

    files = get_changed_files(stage, project_root)
    results: list[CheckResult] = []

    if stage == "commit":
        results.extend(_run_commit_checks(code_config, files, project_root))
    else:
        results.extend(
            _run_push_checks(code_config, files, project_root, build_command)
        )

    elapsed = int((time.monotonic() - start) * 1000)
    passed = all(r.passed for r in results)

    return CheckReport(
        stage=stage,
        passed=passed,
        results=results,
        duration_ms=elapsed,
    )


def _run_commit_checks(
    config: CodeConfig,
    files: list[str],
    project_root: Path,
) -> list[CheckResult]:
    """Run commit-stage checks.

    Args:
        config: CodeConfig with commit settings.
        files: Changed files list.
        project_root: Path to project root.

    Returns:
        List of CheckResults for commit stage.
    """
    results: list[CheckResult] = []

    if config.commit_format:
        results.append(run_precommit("format", files, project_root))

    if config.commit_naming:
        results.append(run_precommit("naming", files, project_root))

    for name, check_item in config.commit_checks.items():
        results.append(run_check(name, check_item, files, project_root))

    return results


def _run_push_checks(
    config: CodeConfig,
    files: list[str],
    project_root: Path,
    build_command: str | None,
) -> list[CheckResult]:
    """Run push-stage checks.

    Args:
        config: CodeConfig with push settings.
        files: Changed files list.
        project_root: Path to project root.
        build_command: Optional build command.

    Returns:
        List of CheckResults for push stage.
    """
    results: list[CheckResult] = []

    if build_command:
        results.append(run_build(build_command, project_root))

    if config.push_lint:
        results.append(run_precommit("lint", files, project_root))

    for name, check_item in config.push_checks.items():
        results.append(run_check(name, check_item, files, project_root))

    return results
