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

from ac_guard.reporter._git_info import get_current_branch, get_remote_repo
from ac_guard.reporter.channel_base import ChannelError, ReportChannel, register_channel

if TYPE_CHECKING:
    from ac_guard.config.models import PrReportConfig

__all__ = ["GitHubChannel"]

_PR_REF_PATTERN = re.compile(r"^refs/pull/(\d+)/")
"""Pattern to extract PR number from GITHUB_REF."""


@register_channel
class GitHubChannel(ReportChannel):
    """Post check reports to GitHub PR comments.

    Repository and PR number are resolved automatically:

    **Repository** (in priority order):
        1. ``GITHUB_REPOSITORY`` environment variable
        2. ``git remote get-url origin`` parsed

    **PR number** (in priority order):
        1. ``AI_GUARD_PR_NUMBER`` environment variable
        2. ``GITHUB_REF`` (``refs/pull/<n>/merge``)
        3. GitHub API query by current branch name

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
        api_url = (config.api_url or self.DEFAULT_API_URL).rstrip("/")
        pr_number = self._get_pr_number(token, repo, api_url)

        url = f"{api_url}/repos/{repo}/issues/{pr_number}/comments"
        self._post_json(url, {"body": markdown}, token)

    def _get_pr_number(self, token: str, repo: str, api_url: str) -> str:
        """Determine the PR number.

        Priority:
            1. ``AI_GUARD_PR_NUMBER`` env var
            2. ``GITHUB_REF`` (``refs/pull/<n>/merge``)
            3. API query by current branch

        Args:
            token: GitHub API token for API query fallback.
            repo: Repository in ``owner/repo`` format.
            api_url: GitHub API base URL.

        Returns:
            PR number as string.

        Raises:
            ChannelError: If PR number cannot be determined.
        """
        # 1. Explicit env var
        pr_number = os.environ.get("AI_GUARD_PR_NUMBER")
        if pr_number:
            return pr_number

        # 2. GITHUB_REF
        github_ref = os.environ.get("GITHUB_REF", "")
        match = _PR_REF_PATTERN.match(github_ref)
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
                data = self._get_json(query_url, token)
                if data and isinstance(data, list) and len(data) > 0:
                    return str(data[0]["number"])
            except ChannelError:
                pass  # Fall through to error

        raise ChannelError(
            "Cannot determine PR number. Set AI_GUARD_PR_NUMBER, "
            "GITHUB_REF (refs/pull/<n>/merge), or push your branch "
            "and open a PR"
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
                f"GitHub token not found: set the {config.token_env} "
                f"environment variable"
            )
        return token

    @staticmethod
    def _get_repository() -> str:
        """Determine the repository.

        Priority:
            1. ``GITHUB_REPOSITORY`` env var
            2. ``git remote get-url origin``

        Returns:
            Repository in ``owner/repo`` format.

        Raises:
            ChannelError: If repository cannot be determined.
        """
        repo = os.environ.get("GITHUB_REPOSITORY")
        if repo:
            return repo

        repo = get_remote_repo()
        if repo:
            return repo

        raise ChannelError(
            "Cannot determine repository. Set GITHUB_REPOSITORY or "
            "ensure git remote 'origin' is configured"
        )

    @staticmethod
    def _post_json(url: str, body: dict, token: str) -> None:
        """POST JSON to a URL with Bearer auth.

        Args:
            url: API endpoint URL.
            body: JSON body dict.
            token: Bearer token.

        Raises:
            ChannelError: On HTTP or connection error.
        """
        data = json.dumps(body).encode("utf-8")
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
    def _get_json(url: str, token: str) -> list | dict | None:
        """GET JSON from a URL with Bearer auth.

        Args:
            url: API endpoint URL.
            token: Bearer token.

        Returns:
            Parsed JSON response.

        Raises:
            ChannelError: On HTTP or connection error.
        """
        req = urllib.request.Request(
            url,
            method="GET",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
            },
        )
        try:
            with urllib.request.urlopen(req) as resp:
                return json.loads(resp.read())
        except HTTPError as exc:
            raise ChannelError(f"GitHub API returned {exc.code}: {exc.reason}") from exc
        except URLError as exc:
            raise ChannelError(
                f"Failed to connect to GitHub API: {exc.reason}"
            ) from exc
