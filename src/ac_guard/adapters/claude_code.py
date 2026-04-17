"""Claude Code Agent adapter implementation.

Claude Code supports full Hook capability:
- PreToolUse Hook for runtime interception (can_block=True)
- User confirmation prompts (can_ask=True)

Rule document: CLAUDE.md
Hook entry: .claude/hooks/interceptor.py (stdin/stdout JSON)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ac_guard.adapters._render import render_hook, render_rule_doc
from ac_guard.adapters.base import AgentAdapter, AgentCapabilities
from ac_guard.shared.types import FileSpec

if TYPE_CHECKING:
    from ac_guard.config.models import BehaviorConfig

__all__ = ["ClaudeCodeAdapter"]


class ClaudeCodeAdapter(AgentAdapter):
    """Adapter for Claude Code AI coding agent."""

    @property
    def name(self) -> str:
        return "claude-code"

    @property
    def capabilities(self) -> AgentCapabilities:
        return AgentCapabilities(can_block=True, can_ask=True)

    def rule_doc_path(self) -> str:
        return "CLAUDE.md"

    def render_rule_doc(self, behavior: BehaviorConfig) -> str:
        """Render behavior rules as Claude Code rule document.

        Returns raw Markdown content without managed-block markers.
        The writer layer (``write_artifacts`` / ``replace_managed_block``)
        owns wrapping so we do not accumulate duplicate markers across
        ``install`` / ``update`` cycles.
        """
        return render_rule_doc("claude_code", behavior)

    def hook_files(self, behavior: BehaviorConfig) -> list[FileSpec]:
        """Generate Claude Code Hook script.

        Uses Jinja2 template (hooks/claude_code.j2) for the Hook script.
        Returns a Python Hook script that:
        - Reads stdin JSON (tool_name, tool_input)
        - Calls Enforcer for policy decision (placeholder for WP2)
        - Returns stdout JSON (hookSpecificOutput.permissionDecision)
        """
        hook_content = render_hook("claude_code", behavior)

        return [
            FileSpec(
                path=".claude/hooks/interceptor.py",
                content=hook_content,
                executable=True,
            ),
        ]
