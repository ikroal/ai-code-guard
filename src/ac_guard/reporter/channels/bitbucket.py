"""BitbucketChannel — post rendered Markdown to Bitbucket PR comments."""

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

__all__ = ["BitbucketChannel"]


@register_channel
class BitbucketChannel(GitPlatformChannel):
    """Post rendered Markdown payloads to Bitbucket PR comments.

    PR ID resolution priority:
        1. ``AI_GUARD_PR_NUMBER`` env var
        2. ``BITBUCKET_PR_ID`` env var
        3. Bitbucket API query by current branch
    """

    name = "bitbucket"
    DEFAULT_API_URL = "https://api.bitbucket.org"
    REPO_ENV_VAR = "BITBUCKET_REPO_FULL_NAME"

    def _api_name(self) -> str:
        return "Bitbucket"

    def _wrap_body(self, payload: str) -> dict:
        """Bitbucket PR comments expect ``{"content": {"raw": ...}}``."""
        return {"content": {"raw": payload}}

    def _resolve_pr(self, token: str, repo: str, api_url: str) -> str:
        # 1. Explicit env var
        pr_id = os.environ.get("AI_GUARD_PR_NUMBER")
        if pr_id:
            return pr_id

        # 2. BITBUCKET_PR_ID
        pr_id = os.environ.get("BITBUCKET_PR_ID")
        if pr_id:
            return pr_id

        # 3. API query by branch
        branch = get_current_branch()
        if branch:
            query_url = f"{api_url}/2.0/repositories/{repo}/pullrequests?state=OPEN"
            try:
                data = get_json(
                    query_url,
                    headers={"Authorization": f"Bearer {token}"},
                    api_name="Bitbucket",
                )
                if data and isinstance(data, dict):
                    for pr in data.get("values", []):
                        source = pr.get("source", {})
                        source_branch = source.get("branch", {})
                        if source_branch.get("name") == branch:
                            return str(pr["id"])
            except ChannelError:
                pass  # Fall through to NoPrContextError

        raise NoPrContextError(
            "Cannot determine PR ID. Set AI_GUARD_PR_NUMBER, "
            "BITBUCKET_PR_ID, or push your branch and open a PR"
        )

    def _post_url(self, api_url: str, repo: str, pr_id: str) -> str:
        return f"{api_url}/2.0/repositories/{repo}/pullrequests/{pr_id}/comments"

    def _auth_headers(self, token: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    def _list_comments_url(self, api_url: str, repo: str, pr_id: str) -> str:
        return f"{api_url}/2.0/repositories/{repo}/pullrequests/{pr_id}/comments"

    def _comment_update_url(
        self, api_url: str, repo: str, pr_id: str, comment_id: str
    ) -> str:
        return f"{api_url}/2.0/repositories/{repo}/pullrequests/{pr_id}/comments/{comment_id}"
