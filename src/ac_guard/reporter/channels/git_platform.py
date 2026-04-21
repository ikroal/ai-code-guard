"""Git platform channel family — shared base class and post_pr_comment.

Four built-in Git platform channels (GitHub, GitLab, Gitea, Bitbucket) share
80% of the PR-comment post flow. :class:`GitPlatformChannel` provides the
template method, common helpers (token + repo resolution, JSON POST via the
retry layer), and a default Markdown body wrapper. Subclasses override the
six differentiating hooks:

    DEFAULT_API_URL, REPO_ENV_VAR          (class attributes)
    _resolve_pr, _post_url, _auth_headers  (platform-specific)
    _wrap_body                             (default {"body": payload})

``post_pr_comment`` is the CLI-facing convenience wrapper: it renders
Markdown, dispatches to the channel registered under ``config.platform``,
and swallows failures to keep the main exit code untouched.
"""

from __future__ import annotations

import os
import sys
from abc import abstractmethod
from typing import TYPE_CHECKING, ClassVar

from ac_guard.reporter.channels._git_info import get_remote_repo
from ac_guard.reporter.channels._http import post_json
from ac_guard.reporter.channels.base import (
    ChannelError,
    NoPrContextError,
    ReportChannel,
    get_channel,
)
from ac_guard.reporter.formatting import format_markdown

if TYPE_CHECKING:
    from typing import Any

    from ac_guard.config.models import PrReportConfig

__all__ = ["GitPlatformChannel", "post_pr_comment"]


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

    def __init__(self, config: PrReportConfig) -> None:
        """Store the PR report configuration for later use by :meth:`output`.

        Args:
            config: PR report configuration.
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
        """Read the API token from ``config.token_env``.

        Returns:
            The token string.

        Raises:
            ChannelError: If the environment variable is not set.
        """
        token = os.environ.get(self.config.token_env)
        if not token:
            raise ChannelError(
                f"{self._api_name()} token not found: set the "
                f"{self.config.token_env} environment variable"
            )
        return token

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


# ---------------------------------------------------------------------------
# post_pr_comment — CLI convenience wrapper
# ---------------------------------------------------------------------------


def post_pr_comment(
    outcome: Any,
    config: PrReportConfig,
    locale: str = "en",
) -> None:
    """Render ``outcome`` as Markdown and post to the configured Git platform.

    Dispatches to the channel registered under ``config.platform`` (one of
    ``"github"`` / ``"gitlab"`` / ``"gitea"`` / ``"bitbucket"``).

    **Non-blocking.** If posting fails for any reason (missing credentials,
    HTTP error, unknown platform), a warning is printed to stderr but no
    exception is raised — the main exit code is not affected.
    :class:`NoPrContextError` (no PR/MR found locally) is silently skipped.

    Args:
        outcome: Check outcome (:class:`ac_guard.checker.StageOutcome`).
        config: PR report configuration. If ``enabled`` is False, this
            function returns immediately.
        locale: Locale for Markdown template (``"en"`` or ``"zh-CN"``).
    """
    if not config.enabled:
        return

    try:
        payload = format_markdown(outcome, locale)
        channel_cls = get_channel(config.platform)
        channel_cls(config=config).output(payload)
    except NoPrContextError:
        return  # Silent skip: no PR in context (typical in local dev)
    except Exception as exc:
        print(f"Warning: PR comment failed to post: {exc}", file=sys.stderr)
