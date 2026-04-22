"""Tests for ac_guard.adapters.kilocode — KiloCode Agent adapter."""

from __future__ import annotations

from ac_guard.adapters.kilocode import KiloCodeAdapter
from ac_guard.config.models import BehaviorConfig, OperationRules, Rule
from ac_guard.domain import managed_block

# ---------------------------------------------------------------------------
# Adapter Properties
# ---------------------------------------------------------------------------


class TestKiloCodeAdapterProperties:
    def test_name(self) -> None:
        adapter = KiloCodeAdapter()
        assert adapter.name == "kilocode"

    def test_capabilities_no_block(self) -> None:
        adapter = KiloCodeAdapter()
        caps = adapter.capabilities
        assert caps.can_block is False

    def test_capabilities_no_ask(self) -> None:
        adapter = KiloCodeAdapter()
        caps = adapter.capabilities
        assert caps.can_ask is False

    def test_rule_doc_path(self) -> None:
        adapter = KiloCodeAdapter()
        # KiloCode uses .kilocode/rules/
        assert ".kilocode/rules/" in adapter.rule_doc_path()
        assert adapter.rule_doc_path().endswith(".md")


# ---------------------------------------------------------------------------
# Rule Document Rendering
# ---------------------------------------------------------------------------


class TestKiloCodeAdapterRenderRuleDoc:
    def test_output_is_raw_content_without_markers(self) -> None:
        """Adapter returns plain Markdown; writer layer adds markers."""
        adapter = KiloCodeAdapter()
        behavior = BehaviorConfig.empty()
        result = adapter.render_rule_doc(behavior)
        assert not managed_block.has(result, path=adapter.rule_doc_path())

    def test_output_structure_with_rules(self) -> None:
        adapter = KiloCodeAdapter()
        behavior = BehaviorConfig(
            read=OperationRules.empty(),
            write=OperationRules.empty(),
            execute=OperationRules(
                forbidden=[Rule(pattern="shell:git push --force*")],
                require_approval=[],
                allow=[],
            ),
        )
        result = adapter.render_rule_doc(behavior)
        assert len(result) > 50


# ---------------------------------------------------------------------------
# Hook Files (None for KiloCode)
# ---------------------------------------------------------------------------


class TestKiloCodeAdapterHookFiles:
    def test_returns_empty_list(self) -> None:
        # KiloCode has no Hook capability
        adapter = KiloCodeAdapter()
        behavior = BehaviorConfig.empty()
        files = adapter.hook_files(behavior)
        assert files == []

    def test_returns_empty_with_rules(self) -> None:
        # Even with rules, no hooks are generated
        adapter = KiloCodeAdapter()
        behavior = BehaviorConfig(
            read=OperationRules.empty(),
            write=OperationRules.empty(),
            execute=OperationRules(
                forbidden=[Rule(pattern="shell:rm -rf /*")],
                require_approval=[],
                allow=[],
            ),
        )
        files = adapter.hook_files(behavior)
        assert files == []
