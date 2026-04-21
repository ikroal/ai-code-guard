"""Reporter module — render check outcomes and deliver them to channels.

Public API surface (conceptually three layers):

- **Formatting** (pure, no I/O): :func:`format_terminal`,
  :func:`format_markdown`, :func:`format_json` render a
  :class:`~ac_guard.checker.StageOutcome` into a string.
- **Channels** (physical output destinations): see
  :mod:`ac_guard.reporter.channels` — each channel implements
  ``output(payload)``.
- **Git-platform convenience**: :func:`post_pr_comment` renders Markdown,
  dispatches to the platform channel, and wraps failures non-blockingly.

Audit logging was extracted to :mod:`ac_guard.audit` (see that module).
"""

from ac_guard.reporter.channels.base import ChannelError
from ac_guard.reporter.channels.git_platform import post_pr_comment
from ac_guard.reporter.formatting import format_json, format_markdown, format_terminal

__all__ = [
    "ChannelError",
    "format_json",
    "format_markdown",
    "format_terminal",
    "post_pr_comment",
]
