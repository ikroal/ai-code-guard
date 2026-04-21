"""ReportChannel ABC, registration, and R4 post_pr_comment API.

Defines the interface for posting check reports to code hosting
platforms (GitHub, GitLab, etc.) as PR comments. Each platform
is implemented as a separate channel file and auto-registered.
"""

from __future__ import annotations

import sys
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from ac_guard.reporter.formatting import format_markdown

if TYPE_CHECKING:
    from typing import Any

    from ac_guard.config.models import PrReportConfig

__all__ = [
    "ChannelError",
    "NoPrContextError",
    "ReportChannel",
    "get_channel",
    "post_pr_comment",
    "register_channel",
]


class ChannelError(Exception):
    """Raised when a report channel operation fails.

    This is caught by ``post_pr_comment`` to avoid affecting
    the main exit code — failures are logged as warnings.
    """


class NoPrContextError(ChannelError):
    """Raised when no PR/MR can be identified in the current context.

    Distinct from generic :class:`ChannelError` because it is an
    expected condition during local development (no PR opened yet)
    and should be silently skipped by :func:`post_pr_comment` —
    not logged as a warning. Real failures such as missing tokens
    or HTTP errors continue to raise plain :class:`ChannelError`.
    """


class ReportChannel(ABC):
    """Abstract base for PR comment posting channels.

    Each subclass handles one platform (GitHub, GitLab, etc.).
    Subclasses must be decorated with :func:`register_channel`
    to be discoverable via :func:`get_channel`.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Platform identifier matching ``output.pr_report.platform``."""

    @abstractmethod
    def send(self, markdown: str, config: PrReportConfig) -> None:
        """Post a Markdown report as a PR comment.

        Args:
            markdown: Rendered Markdown report string.
            config: PR report configuration with platform
                credentials and API endpoint.

        Raises:
            ChannelError: If posting fails (HTTP error,
                missing credentials, no PR detected, etc.).
        """


# ---------------------------------------------------------------------------
# Channel registry
# ---------------------------------------------------------------------------

_CHANNELS: dict[str, type[ReportChannel]] = {}


def register_channel(cls: type[ReportChannel]) -> type[ReportChannel]:
    """Register a ReportChannel subclass by its ``name``.

    Intended as a class decorator::

        @register_channel
        class GitHubChannel(ReportChannel):
            ...

    Args:
        cls: A concrete ReportChannel subclass.

    Returns:
        The same class, unmodified.
    """
    instance = cls()
    _CHANNELS[instance.name] = cls
    return cls


def get_channel(platform: str) -> ReportChannel:
    """Look up a registered channel by platform name.

    Args:
        platform: Platform identifier (e.g. ``"github"``).

    Returns:
        A new instance of the matching channel.

    Raises:
        ChannelError: If no channel is registered for the platform.
    """
    cls = _CHANNELS.get(platform)
    if cls is None:
        available = ", ".join(sorted(_CHANNELS)) or "(none)"
        raise ChannelError(f"Unknown platform '{platform}'. Available: {available}")
    return cls()


# ---------------------------------------------------------------------------
# R4: Public API
# ---------------------------------------------------------------------------


def post_pr_comment(
    report: Any,
    config: PrReportConfig,
    locale: str = "en",
) -> None:
    """Post a check report as a PR comment (R4 primitive).

    Renders the report to Markdown, looks up the appropriate
    channel for the configured platform, and sends the comment.

    **Non-blocking:** If sending fails for any reason (missing
    credentials, no PR detected, HTTP error), a warning is printed
    to stderr but no exception is raised — the main exit code
    is not affected.

    Args:
        report: Aggregated check report to post.
        config: PR report configuration. If ``enabled`` is False,
            this function returns immediately.
        locale: Locale for Markdown template (``"en"`` or ``"zh-CN"``).
    """
    if not config.enabled:
        return

    try:
        markdown = format_markdown(report, locale)
        channel = get_channel(config.platform)
        channel.send(markdown, config)
    except NoPrContextError:
        return  # Silent skip: no PR in context (typical in local dev)
    except Exception as exc:
        print(f"Warning: PR comment failed to post: {exc}", file=sys.stderr)


# Ensure built-in channels are registered on import.
# Dynamic import avoids binding unused module names (would trigger F401).
_BUILTIN_CHANNELS = ("bitbucket", "gitea", "github", "gitlab")


def _register_builtins() -> None:
    """Import built-in channel modules to trigger registration."""
    import importlib

    for name in _BUILTIN_CHANNELS:
        importlib.import_module(f"ac_guard.reporter.channels.{name}")


_register_builtins()
