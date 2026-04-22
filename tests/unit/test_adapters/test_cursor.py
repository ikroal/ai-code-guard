"""Tests for ac_guard.adapters.cursor — Cursor Agent adapter."""

from __future__ import annotations

from ac_guard.adapters.cursor import CursorAdapter
from ac_guard.config.models import BehaviorConfig, OperationRules, Rule
from ac_guard.domain import managed_block

# ---------------------------------------------------------------------------
# Adapter Properties
# ---------------------------------------------------------------------------


class TestCursorAdapterProperties:
    def test_name(self) -> None:
        adapter = CursorAdapter()
        assert adapter.name == "cursor"

    def test_capabilities_can_block_true(self) -> None:
        adapter = CursorAdapter()
        caps = adapter.capabilities
        assert caps.can_block is True

    def test_capabilities_can_ask_false(self) -> None:
        # Cursor has limited ask capability, treated as False
        adapter = CursorAdapter()
        caps = adapter.capabilities
        assert caps.can_ask is False

    def test_rule_doc_path(self) -> None:
        adapter = CursorAdapter()
        # Cursor uses .cursor/rules/ directory with .mdc extension
        assert ".cursor/rules/" in adapter.rule_doc_path()
        assert adapter.rule_doc_path().endswith(".mdc")


# ---------------------------------------------------------------------------
# Rule Document Rendering
# ---------------------------------------------------------------------------


class TestCursorAdapterRenderRuleDoc:
    def test_output_is_raw_content_without_markers(self) -> None:
        """Adapter returns plain .mdc content; writer layer adds markers."""
        adapter = CursorAdapter()
        behavior = BehaviorConfig.empty()
        result = adapter.render_rule_doc(behavior)
        assert not managed_block.has(result, path=adapter.rule_doc_path())

    def test_output_structure_with_rules(self) -> None:
        adapter = CursorAdapter()
        behavior = BehaviorConfig(
            read=OperationRules.empty(),
            write=OperationRules(
                forbidden=[Rule(pattern="file:.git/**", reason="git internal")],
                require_approval=[],
                allow=[Rule(pattern="file:src/**")],
            ),
            execute=OperationRules.empty(),
        )
        result = adapter.render_rule_doc(behavior)
        assert "Write" in result or "write" in result.lower()

    def test_empty_behavior_produces_valid_output(self) -> None:
        adapter = CursorAdapter()
        behavior = BehaviorConfig.empty()
        result = adapter.render_rule_doc(behavior)
        assert len(result) > 0
        assert not managed_block.has(result, path=adapter.rule_doc_path())


# ---------------------------------------------------------------------------
# Hook Files
# ---------------------------------------------------------------------------


class TestCursorAdapterHookFiles:
    def test_returns_hook_files(self) -> None:
        adapter = CursorAdapter()
        behavior = BehaviorConfig.empty()
        files = adapter.hook_files(behavior)
        assert len(files) > 0

    def test_hook_file_paths(self) -> None:
        adapter = CursorAdapter()
        behavior = BehaviorConfig.empty()
        files = adapter.hook_files(behavior)
        paths = [f.path for f in files]
        # Cursor hooks under .cursor/hooks/
        assert any(".cursor/hooks/" in p for p in paths)

    def test_hook_files_have_content(self) -> None:
        adapter = CursorAdapter()
        behavior = BehaviorConfig.empty()
        files = adapter.hook_files(behavior)
        for f in files:
            assert len(f.content) > 0
