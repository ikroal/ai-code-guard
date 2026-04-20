"""Gitea ReportChannel — posts check reports as PR comments.

Uses the Gitea REST API to create issue comments on pull requests.
Supports both gitea.com and self-hosted Gitea instances
via the ``api_url`` configuration.
"""

from __future__ import annotations

import os
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

__all__ = ["GiteaChannel"]


@register_channel
class GiteaChannel(ReportChannel):
    """Post check reports to Gitea PR comments.

    Repository and PR number are resolved automatically:

    **Repository** (in priority order):
        1. ``GITEA_REPOSITORY`` environment variable
        2. ``git remote get-url origin`` parsed

    **PR number** (in priority order):
        1. ``AI_GUARD_PR_NUMBER`` environment variable
        2. Gitea API query by current branch name

    Attributes:
        DEFAULT_API_URL: Default Gitea API base URL.
    """

    DEFAULT_API_URL = "https://gitea.com"

    @property
    def name(self) -> str:
        """Platform identifier."""
        return "gitea"

    def send(self, markdown: str, config: PrReportConfig) -> None:
        """Post markdown as a comment on the associated PR.

        Args:
            markdown: Rendered Markdown report string.
            config: PR report configuration.

        Raises:
            ChannelError: If token is missing, PR cannot be
                identified, or the API request fails.
        """
        token = self._get_token(config)
        repo = self._get_repository()
        api_url = (config.api_url or self.DEFAULT_API_URL).rstrip("/")
        pr_number = self._get_pr_number(token, repo, api_url)

        url = f"{api_url}/api/v1/repos/{repo}/issues/{pr_number}/comments"
        self._post_json(url, {"body": markdown}, token)

    def _get_pr_number(self, token: str, repo: str, api_url: str) -> str:
        """Determine the PR number.

        Priority:
            1. ``AI_GUARD_PR_NUMBER`` env var
            2. API query by current branch

        Args:
            token: Gitea API token for API query fallback.
            repo: Repository in ``owner/repo`` format.
            api_url: Gitea API base URL.

        Returns:
            PR number as string.

        Raises:
            ChannelError: If PR number cannot be determined.
        """
        # 1. Explicit env var
        pr_number = os.environ.get("AI_GUARD_PR_NUMBER")
        if pr_number:
            return pr_number

        # 2. API query by branch
        branch = get_current_branch()
        if branch:
            query_url = f"{api_url}/api/v1/repos/{repo}/pulls?state=open&limit=50"
            try:
                data = self._get_json(query_url, token)
                if data and isinstance(data, list):
                    for pr in data:
                        head = pr.get("head", {})
                        if head.get("label") == branch:
                            return str(pr["number"])
            except ChannelError:
                pass  # Fall through to error

        raise NoPrContextError(
            "Cannot determine PR number. Set AI_GUARD_PR_NUMBER, "
            "or push your branch and open a PR"
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
                f"Gitea token not found: set the {config.token_env} "
                f"environment variable"
            )
        return token

    @staticmethod
    def _get_repository() -> str:
        """Determine the repository.

        Priority:
            1. ``GITEA_REPOSITORY`` env var
            2. ``git remote get-url origin``

        Returns:
            Repository in ``owner/repo`` format.

        Raises:
            ChannelError: If repository cannot be determined.
        """
        repo = os.environ.get("GITEA_REPOSITORY")
        if repo:
            return repo

        repo = get_remote_repo()
        if repo:
            return repo

        raise ChannelError(
            "Cannot determine repository. Set GITEA_REPOSITORY or "
            "ensure git remote 'origin' is configured"
        )

    @staticmethod
    def _post_json(url: str, body: dict, token: str) -> None:
        """POST JSON with token auth via the shared retry layer."""
        request_json(
            url,
            method="POST",
            headers={
                "Authorization": f"token {token}",
                "Content-Type": "application/json",
            },
            body=body,
            api_name="Gitea",
        )

    @staticmethod
    def _get_json(url: str, token: str) -> list | dict | None:
        """GET JSON with token auth via the shared retry layer."""
        return request_json(
            url,
            method="GET",
            headers={"Authorization": f"token {token}"},
            api_name="Gitea",
        )
