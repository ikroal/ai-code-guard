"""Reporter dispatch layer — render + deliver a StageOutcome.

This module is the **single public entry point** of the reporter package.
It sits on top of two implementation layers:

- :mod:`ac_guard.reporter.formatting` — renders ``StageOutcome`` into a
  string (TEXT / MARKDOWN / JSON).
- :mod:`ac_guard.reporter.channels` — delivers a string to a physical
  destination (stdout, file, PR comment).

Callers describe their intent with a single :class:`ReportConfig` that
names the channel, the format, and the locale; :func:`report` picks the
matching formatter and channel, validates the combination, and dispatches.
The lower-level rendering functions and channel classes are intentionally
**not** re-exported from ``ac_guard.reporter`` — they are implementation
details.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from ac_guard.reporter.channels.base import (
    ChannelError,
    NoPrContextError,
    get_channel,
)
from ac_guard.reporter.channels.file import FileChannel
from ac_guard.reporter.channels.terminal import TerminalChannel
from ac_guard.reporter.formatting import format_json, format_markdown, format_terminal

if TYPE_CHECKING:
    from pathlib import Path
    from typing import TextIO

    from ac_guard.domain.models import StageOutcome
    from ac_guard.reporter.channels.base import ReportChannel

__all__ = [
    "FileCfg",
    "FormatKind",
    "GitPlatformCfg",
    "ReportConfig",
    "TerminalCfg",
    "report",
]


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


class FormatKind(StrEnum):
    """Rendering format for a report."""

    TEXT = "text"
    MARKDOWN = "markdown"
    JSON = "json"


@dataclass
class TerminalCfg:
    """Print to a text stream (stdout by default). Format-agnostic."""

    stream: TextIO | None = None  # None ⇒ sys.stdout


@dataclass
class FileCfg:
    """Write to a local file. Parent directory must exist."""

    path: Path


@dataclass
class GitPlatformCfg:
    """Post to a Git-platform PR/MR comment. Format must be MARKDOWN.

    Attributes:
        platform: One of ``"github"`` / ``"gitlab"`` / ``"gitea"`` /
            ``"bitbucket"``.
        token_env: Environment variable name holding the API token.
        api_url: Custom API endpoint for self-hosted instances; ``None``
            uses the platform default.
    """

    platform: str
    token_env: str = "GITHUB_TOKEN"
    api_url: str | None = None


@dataclass
class ReportConfig:
    """Unified delivery intent: channel + format + locale.

    Attributes:
        channel: Target channel configuration (tagged union of
            :class:`TerminalCfg`, :class:`FileCfg`, :class:`GitPlatformCfg`).
        format: Rendering format.
        locale: Template / label locale (``"en"`` or ``"zh-CN"``). Ignored
            by JSON rendering.
    """

    channel: TerminalCfg | FileCfg | GitPlatformCfg
    format: FormatKind = FormatKind.TEXT
    locale: str = "en"


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


_GIT_PLATFORM_FORMATS = frozenset({FormatKind.MARKDOWN})
_TERMINAL_FORMATS = frozenset({FormatKind.TEXT, FormatKind.JSON})
_FILE_FORMATS = frozenset(FormatKind)  # all three allowed


def report(
    outcome: StageOutcome,
    config: ReportConfig,
    *,
    non_blocking: bool = False,
) -> None:
    """Render ``outcome`` and deliver it via the configured channel.

    The ``(channel, format)`` pairing is validated against a fixed matrix:

    =================  ======  ========  ======
    channel / format    TEXT    MARKDOWN  JSON
    =================  ======  ========  ======
    TerminalCfg         yes     no        yes
    FileCfg             yes     yes       yes
    GitPlatformCfg      no      yes       no
    =================  ======  ========  ======

    Args:
        outcome: The :class:`~ac_guard.domain.models.StageOutcome` to report.
        config: Delivery intent (channel + format + locale).
        non_blocking: When ``True``, delivery failures are swallowed —
            :class:`NoPrContextError` silently, every other
            :class:`ChannelError` with a stderr warning. Typical use: PR
            comment posting, where a failed push must not affect the
            caller's exit code.

    Raises:
        ValueError: If the channel-format pair is not in the allowed matrix.
        ChannelError / NoPrContextError: Propagated when ``non_blocking`` is
            ``False`` (the default).
    """
    _validate_combination(config.channel, config.format)

    try:
        payload = _render(outcome, config.format, config.locale)
        channel = _build_channel(config.channel)
        channel.output(payload)
    except NoPrContextError:
        if not non_blocking:
            raise
    except ChannelError as exc:
        if not non_blocking:
            raise
        print(f"Warning: report delivery failed: {exc}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _validate_combination(
    channel: TerminalCfg | FileCfg | GitPlatformCfg, fmt: FormatKind
) -> None:
    """Reject unsupported channel x format pairings early."""
    if isinstance(channel, TerminalCfg) and fmt not in _TERMINAL_FORMATS:
        raise ValueError(
            f"TerminalCfg does not support format={fmt.value!r}; "
            f"use one of {sorted(f.value for f in _TERMINAL_FORMATS)}"
        )
    if isinstance(channel, GitPlatformCfg) and fmt not in _GIT_PLATFORM_FORMATS:
        raise ValueError(f"GitPlatformCfg requires format=markdown (got {fmt.value!r})")
    # FileCfg accepts any FormatKind — nothing to validate.


def _render(outcome: StageOutcome, fmt: FormatKind, locale: str) -> str:
    """Pick the formatter matching ``fmt`` and render."""
    if fmt is FormatKind.TEXT:
        return format_terminal(outcome, locale=locale)
    if fmt is FormatKind.MARKDOWN:
        return format_markdown(outcome, locale=locale)
    return format_json(outcome)


def _build_channel(
    cfg: TerminalCfg | FileCfg | GitPlatformCfg,
) -> ReportChannel:
    """Construct a channel instance from the matching cfg dataclass."""
    if isinstance(cfg, TerminalCfg):
        if cfg.stream is None:
            return TerminalChannel()
        return TerminalChannel(stream=cfg.stream)
    if isinstance(cfg, FileCfg):
        return FileChannel(cfg.path)
    # GitPlatformCfg — look up platform channel class and construct with cfg.
    cls = get_channel(cfg.platform)
    return cls(config=cfg)  # type: ignore[call-arg]
