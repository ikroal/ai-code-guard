"""Git repository info helper for ReportChannel.

Provides functions to extract repository owner/name and current
branch from the local git repo, used as fallback when CI
environment variables are not available.
"""

from __future__ import annotations

import re
import subprocess

__all__ = ["get_current_branch", "get_remote_repo", "parse_repo_url"]

_HTTPS_REPO_PATTERN = re.compile(r"https?://[^/]+/(.+?)(?:\.git)?$")
"""Match HTTPS remote: https://host/owner/repo.git → owner/repo"""

_SSH_REPO_PATTERN = re.compile(r"git@[^:]+:(.+?)(?:\.git)?$")
"""Match SSH remote: git@host:owner/repo.git → owner/repo"""


def parse_repo_url(url: str) -> str | None:
    """Extract ``owner/repo`` from a git remote URL.

    Handles HTTPS and SSH formats. For paths with more than two
    segments (e.g. GitLab nested groups), returns the last two.

    Args:
        url: Git remote URL string.

    Returns:
        ``"owner/repo"`` string, or None if unparseable.
    """
    for pattern in (_HTTPS_REPO_PATTERN, _SSH_REPO_PATTERN):
        match = pattern.match(url.strip())
        if match:
            path = match.group(1)
            # For nested groups (a/b/c/repo), take last two segments
            parts = path.split("/")
            if len(parts) >= 2:
                return f"{parts[-2]}/{parts[-1]}"
            return path
    return None


def get_remote_repo() -> str | None:
    """Get ``owner/repo`` from ``git remote get-url origin``.

    Returns:
        Parsed ``"owner/repo"`` string, or None if git command
        fails or URL is unparseable.
    """
    output = _run_git("remote", "get-url", "origin")
    if output is None:
        return None
    return parse_repo_url(output)


def get_current_branch() -> str | None:
    """Get the current git branch name.

    Returns:
        Branch name string, or None if not on a branch
        or git command fails.
    """
    output = _run_git("branch", "--show-current")
    if output is None:
        return None
    return output.strip() or None


def _run_git(*args: str) -> str | None:
    """Run a git command and return stdout, or None on failure.

    Args:
        args: Git subcommand and arguments.

    Returns:
        Stripped stdout string, or None if the command fails.
    """
    try:
        result = subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
        return result.stdout.strip()
    except (
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        FileNotFoundError,
    ):
        return None
