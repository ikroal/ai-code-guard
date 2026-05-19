"""Git platform channel family — shared base class.

Four built-in Git platform channels (GitHub, GitLab, Gitea, Bitbucket) share
80% of the PR-comment post flow. :class:`GitPlatformChannel` provides the
template method, common helpers (token + repo resolution, JSON POST via the
retry layer), and a default Markdown body wrapper. Subclasses override the
six differentiating hooks:

    DEFAULT_API_URL, REPO_ENV_VAR          (class attributes)
    _resolve_pr, _post_url, _auth_headers  (platform-specific)
    _wrap_body                             (default {"body": payload})

The dispatch-layer convenience wrapper (picking a platform by name,
rendering Markdown, non-blocking wrapping) used to live here but moved to
:mod:`ac_guard.reporter.core` — it is a *dispatch* concern, not a
channel-implementation concern.
"""

from __future__ import annotations

import os
import subprocess
from abc import abstractmethod
from typing import TYPE_CHECKING, ClassVar

from ac_guard.reporter.channels._git_info import get_remote_repo
from ac_guard.reporter.channels._http import post_json
from ac_guard.reporter.channels.base import ChannelError, ReportChannel

if TYPE_CHECKING:
    from ac_guard.reporter.core import GitPlatformCfg

__all__ = ["GitPlatformChannel"]


class GitPlatformChannel(ReportChannel):
    """Shared base for GitHub/GitLab/Gitea/Bitbucket PR-comment channels.

    Subclasses must:

    - Set ``name`` (from :class:`ReportChannel`) to the platform identifier.
    - Set :attr:`DEFAULT_API_URL` and :attr:`REPO_ENV_VAR`.
    - Implement :meth:`_resolve_pr`, :meth:`_post_url`, :meth:`_auth_headers`.
    - Optionally override :meth:`_encode_repo` (URL-encoding for GitLab) and
      :meth:`_wrap_body` (Bitbucket's ``{"content": {"raw": ...}}`` wrapper).
    """

    #: Default API base URL (subclass overrides; stripped of trailing slashes).
    DEFAULT_API_URL: ClassVar[str] = ""

    #: Environment variable that carries the repository identifier
    #: (e.g. ``"GITHUB_REPOSITORY"``, ``"CI_PROJECT_ID"``).
    REPO_ENV_VAR: ClassVar[str] = ""

    def __init__(self, config: GitPlatformCfg) -> None:
        """Store the platform configuration for later use by :meth:`output`.

        Args:
            config: :class:`~ac_guard.reporter.core.GitPlatformCfg` with
                platform / token_env / api_url.
        """
        self.config = config

    # ---- template method ---------------------------------------------------

    def output(self, payload: str) -> None:
        """Post ``payload`` (Markdown) as a comment on the associated PR/MR.

        Args:
            payload: Rendered Markdown string.

        Raises:
            ChannelError: On token/repo/PR-resolution failure or API error.
            NoPrContextError: If no PR/MR can be identified (silent-skip
                condition for local development).
        """
        token = self._read_token()
        repo = self._resolve_repo()
        api_url = (self.config.api_url or self.DEFAULT_API_URL).rstrip("/")
        pr_id = self._resolve_pr(token, repo, api_url)
        url = self._post_url(api_url, repo, pr_id)
        post_json(
            url,
            headers=self._auth_headers(token),
            body=self._wrap_body(payload),
            api_name=self._api_name(),
        )

    # ---- common helpers ----------------------------------------------------

    def _read_token(self) -> str:
        """Read the API token from ``config.token_env`` or ``gh`` CLI.

        Priority:
            1. ``config.token_env`` environment variable
            2. ``gh auth token`` (local development fallback)

        Returns:
            The token string.

        Raises:
            ChannelError: If neither source provides a token.
        """
        token = os.environ.get(self.config.token_env)
        if token:
            return token
        # Fallback: gh CLI (local development)
        try:
            result = subprocess.run(
                ["gh", "auth", "token"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        raise ChannelError(
            f"{self._api_name()} token not found: set the "
            f"{self.config.token_env} environment variable "
            f"or run 'gh auth login'"
        )

    def _resolve_repo(self) -> str:
        """Resolve the repository identifier.

        Priority:
            1. ``REPO_ENV_VAR`` environment variable
            2. ``git remote get-url origin`` parsed

        Subclasses may override :meth:`_encode_repo` to post-process the
        resolved value (e.g. URL-encode for GitLab).

        Returns:
            Platform-specific repository identifier.

        Raises:
            ChannelError: If the repository cannot be determined.
        """
        if self.REPO_ENV_VAR:
            raw = os.environ.get(self.REPO_ENV_VAR)
            if raw:
                return self._encode_repo(raw)
        raw = get_remote_repo()
        if raw:
            return self._encode_repo(raw)
        raise ChannelError(
            f"Cannot determine repository. Set {self.REPO_ENV_VAR} or "
            "ensure git remote 'origin' is configured"
        )

    def _encode_repo(self, repo: str) -> str:
        """Post-process a resolved repo identifier. Default: pass through.

        GitLab overrides this to URL-encode ``owner/repo``.
        """
        return repo

    def _wrap_body(self, payload: str) -> dict:
        """Wrap Markdown payload into the platform's POST body shape.

        Default: ``{"body": payload}`` (GitHub/GitLab/Gitea).
        Bitbucket overrides to ``{"content": {"raw": payload}}``.
        """
        return {"body": payload}

    def _api_name(self) -> str:
        """Human-readable platform name for error / log messages.

        Default: capitalize :attr:`name`. Subclasses can override for
        platforms with mid-word casing (``"GitHub"``, ``"GitLab"``).
        """
        return self.name.capitalize()

    # ---- abstract hooks ----------------------------------------------------

    @abstractmethod
    def _resolve_pr(self, token: str, repo: str, api_url: str) -> str:
        """Resolve the PR/MR identifier.

        Implementations typically check:
            1. ``AI_GUARD_PR_NUMBER`` env var (shared across platforms)
            2. A platform-specific env var (e.g. ``GITHUB_REF``)
            3. An API query by current branch name

        Args:
            token: API token (for the optional API query fallback).
            repo: Already-resolved repository identifier.
            api_url: API base URL (no trailing slash).

        Returns:
            PR / MR identifier as string.

        Raises:
            NoPrContextError: If no PR/MR can be found (silent-skip).
            ChannelError: On other failures during resolution.
        """

    @abstractmethod
    def _post_url(self, api_url: str, repo: str, pr_id: str) -> str:
        """Build the POST URL for creating a PR/MR comment.

        Args:
            api_url: API base URL (no trailing slash).
            repo: Repository identifier (already encoded if necessary).
            pr_id: PR/MR identifier.

        Returns:
            Full POST URL.
        """

    @abstractmethod
    def _auth_headers(self, token: str) -> dict[str, str]:
        """Build the authentication / content-type headers for the POST.

        Args:
            token: API token.

        Returns:
            Dict of request headers.
        """
