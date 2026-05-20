"""OpenAI Codex Agent adapter implementation.

Codex supports full Hook capability via hooks.json / config.toml:
- PreToolUse Hook for runtime interception (can_block=True)
- PermissionRequest for user confirmation (can_ask=True)

Rule document: AGENTS.md (shared with OpenCode per AGENTS.md open standard)
Hook config: .codex/hooks/ac-guard.json
Hook script: .codex/hooks/ac-guard.py (Python, stdin/stdout JSON)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ac_guard.adapters._render import render_hook, render_rule_doc
from ac_guard.adapters.base import AgentAdapter, AgentCapabilities
from ac_guard.domain import FileSpec

if TYPE_CHECKING:
    from ac_guard.config import BehaviorConfig

__all__ = ["CodexAdapter"]


class CodexAdapter(AgentAdapter):
    """Adapter for OpenAI Codex AI coding agent."""

    @property
    def name(self) -> str:
        return "codex"

    @property
    def capabilities(self) -> AgentCapabilities:
        return AgentCapabilities(can_block=True, can_ask=True)

    def rule_doc_path(self) -> str:
        return "AGENTS.md"

    def render_rule_doc(self, behavior: BehaviorConfig) -> str:
        """Render behavior rules as Codex rule document.

        Returns raw Markdown content without managed-block markers.
        The writer layer (``write_artifacts``) owns marker wrapping.
        """
        return render_rule_doc(self, behavior)

    def hook_files(self, behavior: BehaviorConfig) -> list[FileSpec]:
        """Generate Codex Hook configuration and script.

        Returns two files:
        - .codex/hooks/ac-guard.json — hooks.json config (PreToolUse matcher)
        - .codex/hooks/ac-guard.py  — Python policy evaluation script
        """
        hook_content = render_hook(self, behavior)

        return [
            FileSpec(
                path=".codex/hooks/ac-guard.json",
                content=hook_content.split("--- SPLIT ---\n")[0],
                executable=False,
            ),
            FileSpec(
                path=".codex/hooks/ac-guard.py",
                content=hook_content.split("--- SPLIT ---\n")[1],
                executable=True,
            ),
        ]
