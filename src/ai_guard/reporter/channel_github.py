"""GitHub ReportChannel — posts check reports as PR comments.

Uses the GitHub REST API to create issue comments on pull requests.
Supports both github.com and self-hosted GitHub Enterprise instances
via the ``api_url`` configuration.
"""

from __future__ import annotations

import json
import os
import re
import urllib.request
from typing import TYPE_CHECKING
from urllib.error import HTTPError, URLError

from ai_guard.reporter.channel_base import ChannelError, ReportChannel, register_channel

if TYPE_CHECKING:
    from ai_guard.config.models import PrReportConfig

__all__ = ["GitHubChannel"]

_PR_REF_PATTERN = re.compile(r"^refs/pull/(\d+)/")
"""Pattern to extract PR number from GITHUB_REF."""


@register_channel
class GitHubChannel(ReportChannel):
    """Post check reports to GitHub PR comments.

    Requires environment variables:
        - Token: from ``config.token_env`` (default ``GITHUB_TOKEN``)
        - Repository: ``GITHUB_REPOSITORY`` (format ``owner/repo``)
        - PR number: parsed from ``GITHUB_REF`` (``refs/pull/<n>/merge``)
          or ``AI_GUARD_PR_NUMBER`` as fallback

    Attributes:
        DEFAULT_API_URL: Default GitHub API base URL.
    """

    DEFAULT_API_URL = "https://api.github.com"

    @property
    def name(self) -> str:
        """Platform identifier."""
        return "github"

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
        pr_number = self._get_pr_number()
        api_url = (config.api_url or self.DEFAULT_API_URL).rstrip("/")

        url = f"{api_url}/repos/{repo}/issues/{pr_number}/comments"
        data = json.dumps({"body": markdown}).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=data,
            method="POST",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "Content-Type": "application/json",
            },
        )

        try:
            with urllib.request.urlopen(req) as resp:
                resp.read()
        except HTTPError as exc:
            raise ChannelError(f"GitHub API returned {exc.code}: {exc.reason}") from exc
        except URLError as exc:
            raise ChannelError(
                f"Failed to connect to GitHub API: {exc.reason}"
            ) from exc

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
                f"GitHub token not found: set the {config.token_env} "
                f"environment variable"
            )
        return token

    @staticmethod
    def _get_repository() -> str:
        """Read the repository from ``GITHUB_REPOSITORY``.

        Returns:
            Repository in ``owner/repo`` format.

        Raises:
            ChannelError: If the environment variable is not set.
        """
        repo = os.environ.get("GITHUB_REPOSITORY")
        if not repo:
            raise ChannelError("GITHUB_REPOSITORY environment variable not set")
        return repo

    @staticmethod
    def _get_pr_number() -> str:
        """Determine the PR number from environment variables.

        Checks ``GITHUB_REF`` first (``refs/pull/<n>/merge``),
        then falls back to ``AI_GUARD_PR_NUMBER``.

        Returns:
            PR number as string.

        Raises:
            ChannelError: If PR number cannot be determined.
        """
        github_ref = os.environ.get("GITHUB_REF", "")
        match = _PR_REF_PATTERN.match(github_ref)
        if match:
            return match.group(1)

        pr_number = os.environ.get("AI_GUARD_PR_NUMBER")
        if pr_number:
            return pr_number

        raise ChannelError(
            "Cannot determine PR number. Set GITHUB_REF "
            "(refs/pull/<n>/merge) or AI_GUARD_PR_NUMBER"
        )
