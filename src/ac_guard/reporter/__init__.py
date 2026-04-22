"""Reporter — render StageOutcome and deliver to a channel.

Public API (this is the entire surface; anything else is an
implementation detail):

- :func:`report` — the single dispatch entry point.
- :class:`ReportConfig` — unified delivery intent (channel + format + locale).
- :class:`FormatKind` — the three rendering formats.
- :class:`TerminalCfg` / :class:`FileCfg` / :class:`GitPlatformCfg` —
  the three channel configurations (tagged union members).
- :class:`ChannelError` / :class:`NoPrContextError` — delivery exceptions.

Audit logging was extracted to :mod:`ac_guard.audit`.
"""

from ac_guard.reporter.channels.base import ChannelError, NoPrContextError
from ac_guard.reporter.core import (
    FileCfg,
    FormatKind,
    GitPlatformCfg,
    ReportConfig,
    TerminalCfg,
    report,
)

__all__ = [
    "ChannelError",
    "FileCfg",
    "FormatKind",
    "GitPlatformCfg",
    "NoPrContextError",
    "ReportConfig",
    "TerminalCfg",
    "report",
]
