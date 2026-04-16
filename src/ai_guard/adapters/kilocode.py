"""KiloCode Agent adapter implementation.

KiloCode has no Hook capability:
- No runtime interception (can_block=False)
- No user confirmation prompts (can_ask=False)

Rules are soft constraints only, enforced via rule document.

Rule document: .kilocode/rules/behavior.md
"""

from __future__ import annotations

from ai_guard.adapters.base import AgentAdapter, AgentCapabilities
from ai_guard.config.models import BehaviorConfig
from ai_guard.shared.types import FileSpec, wrap_with_managed_block

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

        KiloCode uses .kilocode/rules/ directory for rule documents.
        Output is wrapped with managed block markers.
        WP1.3b will add Jinja2 templates for improved formatting.
        """
        lines: list[str] = []

        # Header
        lines.append("## Behavior Guidelines")
        lines.append("")
        lines.append(
            "The following guidelines define recommended behavior constraints. "
            "Note: KiloCode does not support runtime enforcement — "
            "these are soft constraints."
        )
        lines.append("")

        # Warning about capabilities
        lines.append(
            "> **Warning**: This Agent cannot block operations at runtime. "
            "Please rely on Git Hooks and manual review for enforcement."
        )
        lines.append("")

        # Render each operation type
        for op_name, op_rules in [
            ("Read", behavior.read),
            ("Write", behavior.write),
            ("Execute", behavior.execute),
        ]:
            lines.append(f"### {op_name} Operations")
            lines.append("")

            if op_rules.forbidden:
                lines.append("**Avoid** (sensitive/protected):")
                for rule in op_rules.forbidden:
                    reason = f" — {rule.reason}" if rule.reason else ""
                    lines.append(f"- `{rule.pattern}`{reason}")
                lines.append("")

            if op_rules.require_approval:
                lines.append("**Review Before** (request confirmation):")
                for rule in op_rules.require_approval:
                    msg = f" — {rule.message}" if rule.message else ""
                    lines.append(f"- `{rule.pattern}`{msg}")
                lines.append("")

            if op_rules.allow:
                lines.append("**Permitted**:")
                for rule in op_rules.allow:
                    lines.append(f"- `{rule.pattern}`")
                lines.append("")

        content = "\n".join(lines)
        return wrap_with_managed_block(content)

    def hook_files(self, behavior: BehaviorConfig) -> list[FileSpec]:
        """KiloCode has no Hook capability — returns empty list."""
        return []
