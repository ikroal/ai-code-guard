"""Tests for ac_guard.adapters.copilot — GitHub Copilot Agent adapter."""

from __future__ import annotations

from ac_guard.adapters.copilot import CopilotAdapter
from ac_guard.config.models import BehaviorConfig, OperationRules, Rule
from ac_guard.domain import managed_block

# ---------------------------------------------------------------------------
# Adapter Properties
# ---------------------------------------------------------------------------


class TestCopilotAdapterProperties:
    def test_name(self) -> None:
        adapter = CopilotAdapter()
        assert adapter.name == "copilot"

    def test_capabilities_no_block(self) -> None:
        adapter = CopilotAdapter()
        caps = adapter.capabilities
        assert caps.can_block is False

    def test_capabilities_no_ask(self) -> None:
        adapter = CopilotAdapter()
        caps = adapter.capabilities
        assert caps.can_ask is False

    def test_rule_doc_path(self) -> None:
        adapter = CopilotAdapter()
        # Copilot uses .github/copilot-instructions.md
        assert ".github/" in adapter.rule_doc_path()
        assert "copilot" in adapter.rule_doc_path().lower()


# ---------------------------------------------------------------------------
# Rule Document Rendering
# ---------------------------------------------------------------------------


class TestCopilotAdapterRenderRuleDoc:
    def test_output_is_raw_content_without_markers(self) -> None:
        """Adapter returns plain Markdown; writer layer adds markers."""
        adapter = CopilotAdapter()
        behavior = BehaviorConfig.empty()
        result = adapter.render_rule_doc(behavior)
        assert not managed_block.has(result, path=adapter.rule_doc_path())

    def test_output_structure_with_rules(self) -> None:
        adapter = CopilotAdapter()
        behavior = BehaviorConfig(
            read=OperationRules(
                forbidden=[Rule(pattern="file:.env")],
                require_approval=[],
                allow=[],
            ),
            write=OperationRules.empty(),
            execute=OperationRules.empty(),
        )
        result = adapter.render_rule_doc(behavior)
        # Should contain behavior rules beyond an empty-body baseline.
        assert len(result) > 50


# ---------------------------------------------------------------------------
# Hook Files (None for Copilot)
# ---------------------------------------------------------------------------


class TestCopilotAdapterHookFiles:
    def test_returns_empty_list(self) -> None:
        # Copilot has no Hook capability
        adapter = CopilotAdapter()
        behavior = BehaviorConfig.empty()
        files = adapter.hook_files(behavior)
        assert files == []

    def test_returns_empty_with_rules(self) -> None:
        # Even with rules, no hooks are generated
        adapter = CopilotAdapter()
        behavior = BehaviorConfig(
            read=OperationRules(
                forbidden=[Rule(pattern="file:.env")],
                require_approval=[],
                allow=[],
            ),
            write=OperationRules.empty(),
            execute=OperationRules.empty(),
        )
        files = adapter.hook_files(behavior)
        assert files == []
