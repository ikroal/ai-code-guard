"""GitLab ReportChannel — posts check reports as MR comments.

Uses the GitLab REST API to create note comments on merge requests.
Supports both gitlab.com and self-hosted GitLab instances
via the ``api_url`` configuration.
"""

from __future__ import annotations

import os
import urllib.parse
from typing import TYPE_CHECKING

from ac_guard.reporter._git_info import get_current_branch, get_remote_repo
from ac_guard.reporter._http import request_json
from ac_guard.reporter.channel_base import (
    ChannelError,
    NoPrContextError,
    ReportChannel,
    register_channel,
)

if TYPE_CHECKING:
    from ac_guard.config.models import PrReportConfig

__all__ = ["GitLabChannel"]


@register_channel
class GitLabChannel(ReportChannel):
    """Post check reports to GitLab MR comments.

    Repository and MR number are resolved automatically:

    **Repository** (in priority order):
        1. ``CI_PROJECT_ID`` environment variable
        2. ``git remote get-url origin`` parsed and URL-encoded

    **MR number** (in priority order):
        1. ``AI_GUARD_PR_NUMBER`` environment variable
        2. ``CI_MERGE_REQUEST_IID`` environment variable
        3. GitLab API query by current branch name

    Attributes:
        DEFAULT_API_URL: Default GitLab API base URL.
    """

    DEFAULT_API_URL = "https://gitlab.com"

    @property
    def name(self) -> str:
        """Platform identifier."""
        return "gitlab"

    def send(self, markdown: str, config: PrReportConfig) -> None:
        """Post markdown as a comment on the associated MR.

        Args:
            markdown: Rendered Markdown report string.
            config: PR report configuration.

        Raises:
            ChannelError: If token is missing, MR cannot be
                identified, or the API request fails.
        """
        token = self._get_token(config)
        project_id = self._get_project_id()
        api_url = (config.api_url or self.DEFAULT_API_URL).rstrip("/")
        mr_iid = self._get_mr_iid(token, project_id, api_url)

        url = f"{api_url}/api/v4/projects/{project_id}/merge_requests/{mr_iid}/notes"
        self._post_json(url, {"body": markdown}, token)

    def _get_mr_iid(self, token: str, project_id: str, api_url: str) -> str:
        """Determine the MR IID.

        Priority:
            1. ``AI_GUARD_PR_NUMBER`` env var
            2. ``CI_MERGE_REQUEST_IID`` env var
            3. API query by current branch

        Args:
            token: GitLab API token for API query fallback.
            project_id: Project ID or URL-encoded path.
            api_url: GitLab API base URL.

        Returns:
            MR IID as string.

        Raises:
            ChannelError: If MR IID cannot be determined.
        """
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
                f"{api_url}/api/v4/projects/{project_id}/merge_requests"
                f"?source_branch={urllib.parse.quote(branch, safe='')}"
                f"&state=opened"
            )
            try:
                data = self._get_json(query_url, token)
                if data and isinstance(data, list) and len(data) > 0:
                    return str(data[0]["iid"])
            except ChannelError:
                pass  # Fall through to error

        raise NoPrContextError(
            "Cannot determine MR IID. Set AI_GUARD_PR_NUMBER, "
            "CI_MERGE_REQUEST_IID, or push your branch and open a MR"
        )

    @staticmethod
    def _get_token(config: PrReportConfig) -> str:
        """Read the API token from the environment.

        Args:
            config: PR report config with ``token_env`` field.

        Returns:
            The token string.

        Raises:
            ChannelError: If the environment variable is not set.
        """
        token = os.environ.get(config.token_env)
        if not token:
            raise ChannelError(
                f"GitLab token not found: set the {config.token_env} "
                f"environment variable"
            )
        return token

    @staticmethod
    def _get_project_id() -> str:
        """Determine the project ID.

        Priority:
            1. ``CI_PROJECT_ID`` env var
            2. ``git remote get-url origin`` URL-encoded

        Returns:
            Project ID or URL-encoded ``owner/repo`` path.

        Raises:
            ChannelError: If project ID cannot be determined.
        """
        project_id = os.environ.get("CI_PROJECT_ID")
        if project_id:
            return project_id

        repo = get_remote_repo()
        if repo:
            return urllib.parse.quote(repo, safe="")

        raise ChannelError(
            "Cannot determine project. Set CI_PROJECT_ID or "
            "ensure git remote 'origin' is configured"
        )

    @staticmethod
    def _post_json(url: str, body: dict, token: str) -> None:
        """POST JSON with PRIVATE-TOKEN auth via the shared retry layer."""
        request_json(
            url,
            method="POST",
            headers={
                "PRIVATE-TOKEN": token,
                "Content-Type": "application/json",
            },
            body=body,
            api_name="GitLab",
        )

    @staticmethod
    def _get_json(url: str, token: str) -> list | dict | None:
        """GET JSON with PRIVATE-TOKEN auth via the shared retry layer."""
        return request_json(
            url,
            method="GET",
            headers={"PRIVATE-TOKEN": token},
            api_name="GitLab",
        )
