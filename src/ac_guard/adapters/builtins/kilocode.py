"""KiloCode Agent adapter implementation.

KiloCode has no Hook capability:
- No runtime interception (can_block=False)
- No user confirmation prompts (can_ask=False)

Rules are soft constraints only, enforced via rule document.

Rule document: .kilocode/rules/behavior.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ac_guard.adapters._render import render_rule_doc
from ac_guard.adapters.base import AgentAdapter, AgentCapabilities

if TYPE_CHECKING:
    from ac_guard.config import BehaviorConfig
    from ac_guard.domain import FileSpec

__all__ = ["KiloCodeAdapter"]


class KiloCodeAdapter(AgentAdapter):
    """Adapter for KiloCode AI coding agent."""

    @property
    def name(self) -> str:
        return "kilocode"

    @property
    def capabilities(self) -> AgentCapabilities:
        # KiloCode has no Hook mechanism
        return AgentCapabilities(can_block=False, can_ask=False)

    def rule_doc_path(self) -> str:
        return ".kilocode/rules/behavior.md"

    def render_rule_doc(self, behavior: BehaviorConfig) -> str:
        """Render behavior rules as KiloCode rule document.

        Returns raw Markdown content without managed block markers;
        the writer layer owns marker wrapping.
        """
        return render_rule_doc(self, behavior)

    def hook_files(self, behavior: BehaviorConfig) -> list[FileSpec]:
        """KiloCode has no Hook capability — returns empty list."""
        return []
