"""GitHubChannel — post rendered Markdown to GitHub PR comments."""

from __future__ import annotations

import os
import re

from ac_guard.reporter.channels._git_info import get_current_branch
from ac_guard.reporter.channels._http import get_json
from ac_guard.reporter.channels.base import (
    ChannelError,
    NoPrContextError,
    register_channel,
)
from ac_guard.reporter.channels.git_platform import GitPlatformChannel

__all__ = ["GitHubChannel"]

_PR_REF_PATTERN = re.compile(r"^refs/pull/(\d+)/")
"""Pattern to extract PR number from ``GITHUB_REF``."""


@register_channel
class GitHubChannel(GitPlatformChannel):
    """Post rendered Markdown payloads to GitHub PR comments.

    PR number resolution priority:
        1. ``AI_GUARD_PR_NUMBER`` env var
        2. ``GITHUB_REF`` matching ``refs/pull/<n>/``
        3. GitHub API query by current branch
    """

    name = "github"
    DEFAULT_API_URL = "https://api.github.com"
    REPO_ENV_VAR = "GITHUB_REPOSITORY"

    def _api_name(self) -> str:
        return "GitHub"

    def _resolve_pr(self, token: str, repo: str, api_url: str) -> str:
        # 1. Explicit env var
        pr_number = os.environ.get("AI_GUARD_PR_NUMBER")
        if pr_number:
            return pr_number

        # 2. GITHUB_REF
        match = _PR_REF_PATTERN.match(os.environ.get("GITHUB_REF", ""))
        if match:
            return match.group(1)

        # 3. API query by branch
        branch = get_current_branch()
        if branch:
            owner = repo.split("/")[0] if "/" in repo else repo
            query_url = (
                f"{api_url}/repos/{repo}/pulls"
                f"?head={owner}:{branch}&state=open&per_page=1"
            )
            try:
                data = get_json(
                    query_url,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Accept": "application/vnd.github+json",
                    },
                    api_name="GitHub",
                )
                if data and isinstance(data, list) and len(data) > 0:
                    return str(data[0]["number"])
            except ChannelError:
                pass  # Fall through to NoPrContextError

        raise NoPrContextError(
            "Cannot determine PR number. Set AI_GUARD_PR_NUMBER, "
            "GITHUB_REF (refs/pull/<n>/merge), or push your branch "
            "and open a PR"
        )

    def _post_url(self, api_url: str, repo: str, pr_id: str) -> str:
        return f"{api_url}/repos/{repo}/issues/{pr_id}/comments"

    def _auth_headers(self, token: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
        }
