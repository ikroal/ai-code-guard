"""GitHub Copilot Agent adapter implementation.

GitHub Copilot supports Hook capability via onPreToolUse events:
- Runtime interception via onPreToolUse (can_block=True)
- User confirmation via permission decision (can_ask=True)

Rule document: .github/copilot-instructions.md
Hook entry: .github/hooks/ac-guard.py (Python, stdin/stdout JSON)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ac_guard.adapters._render import render_hook, render_rule_doc
from ac_guard.adapters.base import AgentAdapter, AgentCapabilities
from ac_guard.domain import FileSpec

if TYPE_CHECKING:
    from ac_guard.config import BehaviorConfig

__all__ = ["CopilotAdapter"]


class CopilotAdapter(AgentAdapter):
    """Adapter for GitHub Copilot AI coding agent."""

    @property
    def name(self) -> str:
        return "copilot"

    @property
    def capabilities(self) -> AgentCapabilities:
        return AgentCapabilities(can_block=True, can_ask=True)

    def rule_doc_path(self) -> str:
        return ".github/copilot-instructions.md"

    def render_rule_doc(self, behavior: BehaviorConfig) -> str:
        """Render behavior rules as Copilot instructions.

        Returns raw ``copilot-instructions.md`` content without managed
        block markers; the writer layer owns marker wrapping.
        """
        return render_rule_doc(self, behavior)

    def hook_files(self, behavior: BehaviorConfig) -> list[FileSpec]:
        """Generate Copilot Hook script.

        Uses Jinja2 template (hooks/copilot.j2) for the Hook script.
        Returns a Python Hook script that:
        - Reads stdin JSON (Copilot format: tool_name, tool_input)
        - Calls Action guard for policy decision
        - Outputs stdout JSON (hookSpecificOutput.permissionDecision)
        """
        hook_content = render_hook(self, behavior)

        return [
            FileSpec(
                path=".github/hooks/ac-guard.py",
                content=hook_content,
                executable=True,
            ),
        ]
