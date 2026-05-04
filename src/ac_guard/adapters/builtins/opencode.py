"""OpenCode Agent adapter implementation.

OpenCode supports full Hook capability via plugin events:
- Runtime interception (can_block=True)
- User confirmation prompts (can_ask=True)

Rule document: AGENTS.md
Hook entry: .opencode/plugins/ac-guard.ts (TypeScript plugin)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ac_guard.adapters._render import render_hook, render_rule_doc
from ac_guard.adapters.base import AgentAdapter, AgentCapabilities
from ac_guard.domain import FileSpec

if TYPE_CHECKING:
    from ac_guard.config import BehaviorConfig

__all__ = ["OpenCodeAdapter"]


class OpenCodeAdapter(AgentAdapter):
    """Adapter for OpenCode AI coding agent."""

    @property
    def name(self) -> str:
        return "opencode"

    @property
    def capabilities(self) -> AgentCapabilities:
        return AgentCapabilities(can_block=True, can_ask=True)

    def rule_doc_path(self) -> str:
        return "AGENTS.md"

    def render_rule_doc(self, behavior: BehaviorConfig) -> str:
        """Render behavior rules as OpenCode rule document.

        Returns raw Markdown content without managed block markers;
        the writer layer owns marker wrapping.
        """
        return render_rule_doc("opencode", behavior)

    def hook_files(self, behavior: BehaviorConfig) -> list[FileSpec]:
        """Generate OpenCode TypeScript plugin.

        Uses Jinja2 template (hooks/opencode.j2) for the plugin.
        Returns a TypeScript plugin file that:
        - Intercepts tool calls via OpenCode plugin API
        - Calls Action guard for policy decision (placeholder for WP2)
        - Throws error to block forbidden operations
        """
        plugin_content = render_hook("opencode", behavior)

        return [
            FileSpec(
                path=".opencode/plugins/ac-guard.ts",
                content=plugin_content,
                executable=False,
            ),
        ]
