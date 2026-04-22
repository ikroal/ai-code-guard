"""GitLabChannel — post rendered Markdown to GitLab MR comments."""

from __future__ import annotations

import os
import urllib.parse

from ac_guard.reporter.channels._git_info import get_current_branch
from ac_guard.reporter.channels._http import get_json
from ac_guard.reporter.channels.base import (
    ChannelError,
    NoPrContextError,
    register_channel,
)
from ac_guard.reporter.channels.git_platform import GitPlatformChannel

__all__ = ["GitLabChannel"]


@register_channel
class GitLabChannel(GitPlatformChannel):
    """Post rendered Markdown payloads to GitLab MR notes.

    Project ID resolution priority:
        1. ``CI_PROJECT_ID`` env var
        2. ``git remote get-url origin`` parsed and URL-encoded

    MR IID resolution priority:
        1. ``AI_GUARD_PR_NUMBER`` env var
        2. ``CI_MERGE_REQUEST_IID`` env var
        3. GitLab API query by current branch
    """

    name = "gitlab"
    DEFAULT_API_URL = "https://gitlab.com"
    REPO_ENV_VAR = "CI_PROJECT_ID"

    def _api_name(self) -> str:
        return "GitLab"

    def _encode_repo(self, repo: str) -> str:
        """URL-encode ``owner/repo`` for embedding in the API path.

        Integer project IDs (from ``CI_PROJECT_ID``) are unchanged by
        percent-encoding, so this is safe to apply uniformly.
        """
        return urllib.parse.quote(repo, safe="")

    def _resolve_pr(self, token: str, repo: str, api_url: str) -> str:
        # 1. Explicit env var
        mr_iid = os.environ.get("AI_GUARD_PR_NUMBER")
        if mr_iid:
            return mr_iid

        # 2. CI_MERGE_REQUEST_IID
        mr_iid = os.environ.get("CI_MERGE_REQUEST_IID")
        if mr_iid:
            return mr_iid

        # 3. API query by branch
        branch = get_current_branch()
        if branch:
            query_url = (
                f"{api_url}/api/v4/projects/{repo}/merge_requests"
                f"?source_branch={urllib.parse.quote(branch, safe='')}"
                f"&state=opened"
            )
            try:
                data = get_json(
                    query_url,
                    headers={"PRIVATE-TOKEN": token},
                    api_name="GitLab",
                )
                if data and isinstance(data, list) and len(data) > 0:
                    return str(data[0]["iid"])
            except ChannelError:
                pass  # Fall through to NoPrContextError

        raise NoPrContextError(
            "Cannot determine MR IID. Set AI_GUARD_PR_NUMBER, "
            "CI_MERGE_REQUEST_IID, or push your branch and open a MR"
        )

    def _post_url(self, api_url: str, repo: str, pr_id: str) -> str:
        return f"{api_url}/api/v4/projects/{repo}/merge_requests/{pr_id}/notes"

    def _auth_headers(self, token: str) -> dict[str, str]:
        return {
            "PRIVATE-TOKEN": token,
            "Content-Type": "application/json",
        }
