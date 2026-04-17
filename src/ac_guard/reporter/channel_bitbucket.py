"""Bitbucket ReportChannel — posts check reports as PR comments.

Uses the Bitbucket REST API to create comments on pull requests.
Supports both bitbucket.org and self-hosted Bitbucket instances
via the ``api_url`` configuration.
"""

from __future__ import annotations

import json
import os
import urllib.request
from typing import TYPE_CHECKING
from urllib.error import HTTPError, URLError

from ac_guard.reporter._git_info import get_current_branch, get_remote_repo
from ac_guard.reporter.channel_base import (
    ChannelError,
    NoPrContextError,
    ReportChannel,
    register_channel,
)

if TYPE_CHECKING:
    from ac_guard.config.models import PrReportConfig

__all__ = ["BitbucketChannel"]


@register_channel
class BitbucketChannel(ReportChannel):
    """Post check reports to Bitbucket PR comments.

    Repository and PR number are resolved automatically:

    **Repository** (in priority order):
        1. ``BITBUCKET_REPO_FULL_NAME`` environment variable
        2. ``git remote get-url origin`` parsed

    **PR number** (in priority order):
        1. ``AI_GUARD_PR_NUMBER`` environment variable
        2. ``BITBUCKET_PR_ID`` environment variable
        3. Bitbucket API query by current branch name

    Attributes:
        DEFAULT_API_URL: Default Bitbucket API base URL.
    """

    DEFAULT_API_URL = "https://api.bitbucket.org"

    @property
    def name(self) -> str:
        """Platform identifier."""
        return "bitbucket"

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
        pr_id = self._get_pr_id(token, repo, api_url)

        url = f"{api_url}/2.0/repositories/{repo}/pullrequests/{pr_id}/comments"
        self._post_json(url, {"content": {"raw": markdown}}, token)

    def _get_pr_id(self, token: str, repo: str, api_url: str) -> str:
        """Determine the PR ID.

        Priority:
            1. ``AI_GUARD_PR_NUMBER`` env var
            2. ``BITBUCKET_PR_ID`` env var
            3. API query by current branch

        Args:
            token: Bitbucket API token for API query fallback.
            repo: Repository in ``workspace/repo`` format.
            api_url: Bitbucket API base URL.

        Returns:
            PR ID as string.

        Raises:
            ChannelError: If PR ID cannot be determined.
        """
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
                data = self._get_json(query_url, token)
                if data and isinstance(data, dict):
                    for pr in data.get("values", []):
                        source = pr.get("source", {})
                        source_branch = source.get("branch", {})
                        if source_branch.get("name") == branch:
                            return str(pr["id"])
            except ChannelError:
                pass  # Fall through to error

        raise NoPrContextError(
            "Cannot determine PR ID. Set AI_GUARD_PR_NUMBER, "
            "BITBUCKET_PR_ID, or push your branch and open a PR"
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
                f"Bitbucket token not found: set the {config.token_env} "
                f"environment variable"
            )
        return token

    @staticmethod
    def _get_repository() -> str:
        """Determine the repository.

        Priority:
            1. ``BITBUCKET_REPO_FULL_NAME`` env var
            2. ``git remote get-url origin``

        Returns:
            Repository in ``workspace/repo`` format.

        Raises:
            ChannelError: If repository cannot be determined.
        """
        repo = os.environ.get("BITBUCKET_REPO_FULL_NAME")
        if repo:
            return repo

        repo = get_remote_repo()
        if repo:
            return repo

        raise ChannelError(
            "Cannot determine repository. Set BITBUCKET_REPO_FULL_NAME or "
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
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req) as resp:
                resp.read()
        except HTTPError as exc:
            raise ChannelError(
                f"Bitbucket API returned {exc.code}: {exc.reason}"
            ) from exc
        except URLError as exc:
            raise ChannelError(
                f"Failed to connect to Bitbucket API: {exc.reason}"
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
            },
        )
        try:
            with urllib.request.urlopen(req) as resp:
                return json.loads(resp.read())
        except HTTPError as exc:
            raise ChannelError(
                f"Bitbucket API returned {exc.code}: {exc.reason}"
            ) from exc
        except URLError as exc:
            raise ChannelError(
                f"Failed to connect to Bitbucket API: {exc.reason}"
            ) from exc
