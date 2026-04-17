"""Ruleset git fetch operations for AI Code Guard.

Handles cloning rulesets from git repositories into the local cache
directory, with support for tag/branch/commit version pinning.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from ac_guard.ruleset.exceptions import RulesetFetchError, RulesetValidationError

if TYPE_CHECKING:
    from ac_guard.ruleset.models import RulesetRef

__all__ = ["fetch_ruleset", "validate_ruleset_dir"]

_GIT_TIMEOUT = 60
"""Timeout in seconds for git operations."""

_SHA_PATTERN = re.compile(r"^[0-9a-f]{7,40}$")
"""Pattern matching a plausible commit SHA (7-40 hex chars)."""


def fetch_ruleset(ref: RulesetRef, cache_root: Path) -> Path:
    """Clone or re-clone a ruleset into the local cache.

    If the target directory already exists it is removed before
    cloning. After a successful clone, the directory is validated
    and a ``.ruleset-meta.json`` metadata file is written.

    Args:
        ref: Parsed ruleset reference with URL, name, and version.
        cache_root: Path to the cache directory
            (e.g. ``<project>/.ac-guard/cache/``).

    Returns:
        Path to the cloned ruleset directory.

    Raises:
        RulesetFetchError: If git clone or checkout fails.
        RulesetValidationError: If the cloned directory lacks
            a valid ``guard.yaml``.
    """
    target = cache_root / ref.name

    # Remove existing to ensure clean state
    if target.exists():
        shutil.rmtree(target, onerror=_rm_readonly)

    # Clone
    if ref.version is None:
        _run_git(["clone", "--depth", "1", ref.url, str(target)])
    elif _is_commit_sha(ref.version):
        # Full clone needed for arbitrary commit checkout
        _run_git(["clone", ref.url, str(target)])
        _run_git(["checkout", ref.version], cwd=target)
    else:
        # Tag or branch — shallow clone
        _run_git(
            ["clone", "--depth", "1", "--branch", ref.version, ref.url, str(target)]
        )

    # Validate
    validate_ruleset_dir(target)

    # Write metadata
    _write_meta(target, ref)

    return target


def validate_ruleset_dir(ruleset_dir: Path) -> None:
    """Verify a ruleset directory contains a ``guard.yaml``.

    Args:
        ruleset_dir: Path to the cloned ruleset directory.

    Raises:
        RulesetValidationError: If ``guard.yaml`` is missing.
    """
    if not (ruleset_dir / "guard.yaml").is_file():
        raise RulesetValidationError(
            ruleset_dir.name,
            "guard.yaml not found in ruleset directory",
        )


def _is_commit_sha(version: str) -> bool:
    """Check if a version string looks like a commit SHA.

    A commit SHA is 7-40 lowercase hexadecimal characters.

    Args:
        version: The version string to check.

    Returns:
        True if the version matches the SHA pattern.
    """
    return bool(_SHA_PATTERN.match(version))


def _run_git(
    args: list[str],
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a git subprocess command.

    Args:
        args: Git subcommand and arguments (without the ``git`` prefix).
        cwd: Working directory for the command.

    Returns:
        The completed process result.

    Raises:
        RulesetFetchError: If the git command exits with non-zero code.
    """
    cmd = ["git", *args]
    try:
        return subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        # Extract URL from args for error message
        url = next((a for a in args if "://" in a or a.startswith("git@")), str(args))
        raise RulesetFetchError(str(url), exc.stderr) from exc
    except subprocess.TimeoutExpired as exc:
        raise RulesetFetchError(
            str(args), f"git command timed out after {_GIT_TIMEOUT}s"
        ) from exc


def _write_meta(target: Path, ref: RulesetRef) -> None:
    """Write ``.ruleset-meta.json`` with fetch metadata.

    Args:
        target: The cloned ruleset directory.
        ref: The parsed ruleset reference.
    """
    meta = {
        "url": ref.url,
        "version": ref.version,
        "fetched_at": datetime.now(tz=timezone.utc).isoformat(),
    }
    (target / ".ruleset-meta.json").write_text(
        json.dumps(meta, indent=2) + "\n",
        encoding="utf-8",
    )


def _rm_readonly(_func: object, path: str, _exc_info: object) -> None:
    """Error handler for shutil.rmtree on read-only files (Windows .git)."""
    import stat

    Path(path).chmod(stat.S_IWRITE)
    Path(path).unlink()
