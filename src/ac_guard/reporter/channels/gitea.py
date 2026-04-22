"""GiteaChannel — post rendered Markdown to Gitea PR comments."""

from __future__ import annotations

import os

from ac_guard.reporter.channels._git_info import get_current_branch
from ac_guard.reporter.channels._http import get_json
from ac_guard.reporter.channels.base import (
    ChannelError,
    NoPrContextError,
    register_channel,
)
from ac_guard.reporter.channels.git_platform import GitPlatformChannel

__all__ = ["GiteaChannel"]


@register_channel
class GiteaChannel(GitPlatformChannel):
    """Post rendered Markdown payloads to Gitea PR comments.

    PR number resolution priority:
        1. ``AI_GUARD_PR_NUMBER`` env var
        2. Gitea API query by current branch (``head.label``)
    """

    name = "gitea"
    DEFAULT_API_URL = "https://gitea.com"
    REPO_ENV_VAR = "GITEA_REPOSITORY"

    def _api_name(self) -> str:
        return "Gitea"

    def _resolve_pr(self, token: str, repo: str, api_url: str) -> str:
        # 1. Explicit env var
        pr_number = os.environ.get("AI_GUARD_PR_NUMBER")
        if pr_number:
            return pr_number

        # 2. API query by branch
        branch = get_current_branch()
        if branch:
            query_url = f"{api_url}/api/v1/repos/{repo}/pulls?state=open&limit=50"
            try:
                data = get_json(
                    query_url,
                    headers={"Authorization": f"token {token}"},
                    api_name="Gitea",
                )
                if data and isinstance(data, list):
                    for pr in data:
                        head = pr.get("head", {})
                        if head.get("label") == branch:
                            return str(pr["number"])
            except ChannelError:
                pass  # Fall through to NoPrContextError

        raise NoPrContextError(
            "Cannot determine PR number. Set AI_GUARD_PR_NUMBER, "
            "or push your branch and open a PR"
        )

    def _post_url(self, api_url: str, repo: str, pr_id: str) -> str:
        return f"{api_url}/api/v1/repos/{repo}/issues/{pr_id}/comments"

    def _auth_headers(self, token: str) -> dict[str, str]:
        return {
            "Authorization": f"token {token}",
            "Content-Type": "application/json",
        }
