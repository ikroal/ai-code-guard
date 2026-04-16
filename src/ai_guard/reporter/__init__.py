"""Reporter module — audit logging, report formatting, and PR posting."""

from ai_guard.reporter.audit import append_audit_log, apply_retention
from ai_guard.reporter.channel_base import ChannelError, post_pr_comment
from ai_guard.reporter.formatting import format_gate, format_markdown, format_terminal

__all__ = [
    "ChannelError",
    "append_audit_log",
    "apply_retention",
    "format_gate",
    "format_markdown",
    "format_terminal",
    "post_pr_comment",
]
