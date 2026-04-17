"""Reporter module — audit logging, report formatting, and PR posting."""

from ac_guard.reporter.audit import append_audit_log, apply_retention
from ac_guard.reporter.channel_base import ChannelError, post_pr_comment
from ac_guard.reporter.formatting import (
    format_gate,
    format_json,
    format_markdown,
    format_terminal,
)

__all__ = [
    "ChannelError",
    "append_audit_log",
    "apply_retention",
    "format_gate",
    "format_json",
    "format_markdown",
    "format_terminal",
    "post_pr_comment",
]
