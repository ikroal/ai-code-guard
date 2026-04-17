"""Cursor Agent adapter implementation.

Cursor supports Hook capability with limitations:
- Runtime interception (can_block=True)
- Limited ask capability (can_ask=False — treated as deny)

Rule document: .cursor/rules/behavior.mdc (Cursor's .mdc format)
Hook entry: .cursor/hooks/check.sh (stdin/stdout JSON)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ac_guard.adapters._render import render_hook, render_rule_doc
from ac_guard.adapters.base import AgentAdapter, AgentCapabilities
from ac_guard.shared.types import FileSpec, wrap_with_managed_block

if TYPE_CHECKING:
    from ac_guard.config.models import BehaviorConfig

__all__ = ["CursorAdapter"]


class CursorAdapter(AgentAdapter):
    """Adapter for Cursor AI coding agent."""

    @property
    def name(self) -> str:
        return "cursor"

    @property
    def capabilities(self) -> AgentCapabilities:
        # Cursor has limited ask capability, treated as False
        return AgentCapabilities(can_block=True, can_ask=False)

    def rule_doc_path(self) -> str:
        return ".cursor/rules/behavior.mdc"

    def render_rule_doc(self, behavior: BehaviorConfig) -> str:
        """Render behavior rules as Cursor rule document.

        Uses Jinja2 template (cursor.mdc.j2) for formatting.
        Cursor uses .mdc format with frontmatter.
        Output is wrapped with managed block markers.
        """
        content = render_rule_doc("cursor", behavior)
        return wrap_with_managed_block(content)

    def hook_files(self, behavior: BehaviorConfig) -> list[FileSpec]:
        """Generate Cursor Hook script.

        Uses Jinja2 template (hooks/cursor.j2) for the Hook script.
        Returns a shell script that:
        - Reads stdin JSON (Cursor format)
        - Calls Enforcer for policy decision (placeholder for WP2)
        - Returns JSON output
        """
        hook_content = render_hook("cursor", behavior)

        return [
            FileSpec(
                path=".cursor/hooks/check.sh",
                content=hook_content,
                executable=True,
            ),
        ]
