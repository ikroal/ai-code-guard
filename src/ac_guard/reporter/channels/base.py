"""ReportChannel ABC, registry, and post_pr_comment entry point.

Channel = physical output destination (terminal, file, Git platform PR
comment). Each channel implements ``output(payload: str)`` — it receives
an already-rendered string and delivers it to its destination. Channels
do not render; formatting stays in :mod:`ac_guard.reporter.formatting`.
"""

from __future__ import annotations

import sys
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, ClassVar

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
    """Raised when a channel's ``output`` fails (I/O, auth, missing PR, ...)."""


class NoPrContextError(ChannelError):
    """Raised when a Git-platform channel cannot identify a PR / MR.

    Distinct from generic :class:`ChannelError` because it is an expected
    condition during local development (no PR opened yet) and is silently
    skipped by :func:`post_pr_comment` — not logged as a warning.
    """


class ReportChannel(ABC):
    """Abstract base for report output channels.

    Subclasses must:
        1. Set the ``name`` class attribute to a unique platform-style identifier
           (e.g. ``"terminal"``, ``"github"``).
        2. Implement :meth:`output` — deliver a rendered string payload to the
           channel's physical destination.

    Subclasses are registered via :func:`register_channel` so that they are
    discoverable through :func:`get_channel`.
    """

    name: ClassVar[str] = ""

    @abstractmethod
    def output(self, payload: str) -> None:
        """Deliver ``payload`` to this channel's physical destination.

        Raises:
            ChannelError: If delivery fails.
        """


# ---------------------------------------------------------------------------
# Channel registry
# ---------------------------------------------------------------------------

_CHANNELS: dict[str, type[ReportChannel]] = {}


def register_channel(cls: type[ReportChannel]) -> type[ReportChannel]:
    """Register a concrete :class:`ReportChannel` subclass.

    Intended as a class decorator::

        @register_channel
        class GitHubChannel(ReportChannel):
            name = "github"
            ...

    Args:
        cls: A concrete :class:`ReportChannel` subclass with a non-empty
            ``name`` class attribute.

    Returns:
        The same class, unmodified.

    Raises:
        TypeError: If ``cls.name`` is empty.
    """
    if not cls.name:
        raise TypeError(f"{cls.__name__} must set a non-empty 'name' class attribute")
    _CHANNELS[cls.name] = cls
    return cls


def get_channel(name: str) -> type[ReportChannel]:
    """Look up a registered channel class by its ``name``.

    Args:
        name: Channel identifier (e.g. ``"github"``, ``"terminal"``).

    Returns:
        The registered channel class. Caller is responsible for
        constructing an instance with channel-specific arguments.

    Raises:
        ChannelError: If no channel is registered under ``name``.
    """
    cls = _CHANNELS.get(name)
    if cls is None:
        available = ", ".join(sorted(_CHANNELS)) or "(none)"
        raise ChannelError(f"Unknown channel '{name}'. Available: {available}")
    return cls


# ---------------------------------------------------------------------------
# post_pr_comment — Git Platform convenience wrapper
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


# ---------------------------------------------------------------------------
# Built-in channel registration
# ---------------------------------------------------------------------------

# Ensure built-in channels are registered on import.
# Dynamic import avoids binding unused module names (would trigger F401).
_BUILTIN_CHANNELS = ("bitbucket", "gitea", "github", "gitlab")


def _register_builtins() -> None:
    """Import built-in channel modules to trigger registration."""
    import importlib

    for name in _BUILTIN_CHANNELS:
        importlib.import_module(f"ac_guard.reporter.channels.{name}")


_register_builtins()
