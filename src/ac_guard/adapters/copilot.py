"""GitHub Copilot Agent adapter implementation.

GitHub Copilot has no Hook capability:
- No runtime interception (can_block=False)
- No user confirmation prompts (can_ask=False)

Rules are soft constraints only, enforced via rule document.

Rule document: .github/copilot-instructions.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ac_guard.adapters._render import render_rule_doc
from ac_guard.adapters.base import AgentAdapter, AgentCapabilities

if TYPE_CHECKING:
    from ac_guard.config.models import BehaviorConfig
    from ac_guard.shared.types import FileSpec

__all__ = ["CopilotAdapter"]


class CopilotAdapter(AgentAdapter):
    """Adapter for GitHub Copilot AI coding agent."""

    @property
    def name(self) -> str:
        return "copilot"

    @property
    def capabilities(self) -> AgentCapabilities:
        # Copilot has no Hook mechanism
        return AgentCapabilities(can_block=False, can_ask=False)

    def rule_doc_path(self) -> str:
        return ".github/copilot-instructions.md"

    def render_rule_doc(self, behavior: BehaviorConfig) -> str:
        """Render behavior rules as Copilot instructions.

        Returns raw ``copilot-instructions.md`` content without managed
        block markers; the writer layer owns marker wrapping.
        """
        return render_rule_doc("copilot", behavior)

    def hook_files(self, behavior: BehaviorConfig) -> list[FileSpec]:
        """Copilot has no Hook capability — returns empty list."""
        return []
