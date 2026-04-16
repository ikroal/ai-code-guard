"""Tests for ai_guard.adapters.opencode — OpenCode Agent adapter."""

from __future__ import annotations

from ai_guard.adapters.opencode import OpenCodeAdapter
from ai_guard.config.models import BehaviorConfig, OperationRules, Rule
from ai_guard.shared.types import MARKER_BEGIN, MARKER_END

# ---------------------------------------------------------------------------
# Adapter Properties
# ---------------------------------------------------------------------------


class TestOpenCodeAdapterProperties:
    def test_name(self) -> None:
        adapter = OpenCodeAdapter()
        assert adapter.name == "opencode"

    def test_capabilities(self) -> None:
        adapter = OpenCodeAdapter()
        caps = adapter.capabilities
        assert caps.can_block is True
        assert caps.can_ask is True

    def test_rule_doc_path(self) -> None:
        adapter = OpenCodeAdapter()
        assert adapter.rule_doc_path() == "AGENTS.md"


# ---------------------------------------------------------------------------
# Rule Document Rendering
# ---------------------------------------------------------------------------


class TestOpenCodeAdapterRenderRuleDoc:
    def test_output_has_managed_block_markers(self) -> None:
        adapter = OpenCodeAdapter()
        behavior = BehaviorConfig.empty()
        result = adapter.render_rule_doc(behavior)
        assert MARKER_BEGIN in result
        assert MARKER_END in result

    def test_output_structure_with_rules(self) -> None:
        adapter = OpenCodeAdapter()
        behavior = BehaviorConfig(
            read=OperationRules.empty(),
            write=OperationRules.empty(),
            execute=OperationRules(
                forbidden=[Rule(pattern="shell:rm -rf*", reason="dangerous")],
                require_approval=[],
                allow=[Rule(pattern="shell:git status*")],
            ),
        )
        result = adapter.render_rule_doc(behavior)
        assert "Execute" in result or "execute" in result.lower()


# ---------------------------------------------------------------------------
# Hook Files
# ---------------------------------------------------------------------------


class TestOpenCodeAdapterHookFiles:
    def test_returns_hook_files(self) -> None:
        adapter = OpenCodeAdapter()
        behavior = BehaviorConfig.empty()
        files = adapter.hook_files(behavior)
        assert len(files) > 0

    def test_hook_file_paths(self) -> None:
        adapter = OpenCodeAdapter()
        behavior = BehaviorConfig.empty()
        files = adapter.hook_files(behavior)
        paths = [f.path for f in files]
        # OpenCode plugin under .opencode/plugins/
        assert any(".opencode/plugins/" in p for p in paths)

    def test_hook_files_have_content(self) -> None:
        adapter = OpenCodeAdapter()
        behavior = BehaviorConfig.empty()
        files = adapter.hook_files(behavior)
        for f in files:
            assert len(f.content) > 0
