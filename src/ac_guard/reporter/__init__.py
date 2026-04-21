"""Reporter module — report formatting and PR posting.

Audit logging was extracted to :mod:`ac_guard.audit` as an
independent module with its own primitive-derived API (see that
module for details).
"""

from ac_guard.reporter.channels.base import ChannelError
from ac_guard.reporter.channels.git_platform import post_pr_comment
from ac_guard.reporter.formatting import (
    format_gate,
    format_json,
    format_markdown,
    format_terminal,
)

__all__ = [
    "ChannelError",
    "format_gate",
    "format_json",
    "format_markdown",
    "format_terminal",
    "post_pr_comment",
]
