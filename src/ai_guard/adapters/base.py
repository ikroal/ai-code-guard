"""AgentAdapter abstract base class.

Defines the contract for all Agent-specific file generation strategies.
Each adapter declares the Agent's Hook capabilities and implements
methods for generating rule documents and Hook files.

Shared types (FileSpec, managed block markers) are defined in
ai_guard.shared.types to avoid circular dependencies.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from ai_guard.config.models import BehaviorConfig
from ai_guard.shared.types import FileSpec  # Shared type

__all__ = [
    "AgentAdapter",
    "AgentCapabilities",
]


# ---------------------------------------------------------------------------
# Agent Capabilities
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AgentCapabilities:
    """Declaration of an Agent's Hook mechanism capabilities.

    Attributes:
        can_block: Whether the Agent can block operations at runtime.
            If True, forbidden rules trigger deny decisions.
            If False, rules are only soft constraints in rule documents.
        can_ask: Whether the Agent can prompt for user confirmation.
            If True, require_approval rules trigger ask decisions.
            If False, require_approval rules are downgraded to deny.
    """

    can_block: bool
    can_ask: bool


class AgentAdapter(ABC):
    """Abstract base class for Agent-specific artifact generation.

    Each AgentAdapter provides the Agent-specific strategy for:
    - Declaring Hook capabilities (can_block / can_ask)
    - Generating rule document content and file path
    - Generating Hook script and configuration files

    The Generator module calls these methods during install/update
    to produce Agent-specific artifacts.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Agent identifier used in --agent CLI argument.

        Must be lowercase with hyphens between words.
        Examples: "claude-code", "cursor", "opencode".
        """

    @property
    @abstractmethod
    def capabilities(self) -> AgentCapabilities:
        """Declaration of this Agent's Hook mechanism capabilities."""

    @abstractmethod
    def rule_doc_path(self) -> str:
        """Return the rule document file path relative to project root.

        Examples:
        - "CLAUDE.md" for Claude Code
        - ".cursor/rules/behavior.mdc" for Cursor
        - ".github/copilot-instructions.md" for GitHub Copilot
        """

    @abstractmethod
    def render_rule_doc(self, behavior: BehaviorConfig) -> str:
        """Render behavior rules as Agent-specific rule document content.

        The output must be wrapped with managed block markers:
        <!-- AI-GUARD:BEGIN --> and <!-- AI-GUARD:END -->.

        Args:
            behavior: BehaviorConfig containing read/write/execute rules.

        Returns:
            Markdown content string for the rule document.
        """

    @abstractmethod
    def hook_files(self, behavior: BehaviorConfig) -> list[FileSpec]:
        """Generate Agent-specific Hook scripts and configuration files.

        Agents without Hook capability (can_block=False) return empty list.
        Agents with Hook capability return FileSpecs for:
        - Hook script files (e.g., .claude/hooks/interceptor.py)
        - Hook configuration files if needed

        Args:
            behavior: BehaviorConfig containing behavior rules.
                (Hook scripts may embed rules or reference policy.json)

        Returns:
            List of FileSpec objects for Hook-related files.
        """
