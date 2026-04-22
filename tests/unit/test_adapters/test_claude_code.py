"""Tests for ac_guard.adapters.claude_code — Claude Code Agent adapter."""

from __future__ import annotations

from ac_guard.adapters.claude_code import ClaudeCodeAdapter
from ac_guard.config.models import BehaviorConfig, OperationRules, Rule
from ac_guard.domain import managed_block

# ---------------------------------------------------------------------------
# Adapter Properties
# ---------------------------------------------------------------------------


class TestClaudeCodeAdapterProperties:
    def test_name(self) -> None:
        adapter = ClaudeCodeAdapter()
        assert adapter.name == "claude-code"

    def test_capabilities(self) -> None:
        adapter = ClaudeCodeAdapter()
        caps = adapter.capabilities
        assert caps.can_block is True
        assert caps.can_ask is True

    def test_rule_doc_path(self) -> None:
        adapter = ClaudeCodeAdapter()
        assert adapter.rule_doc_path() == "CLAUDE.md"


# ---------------------------------------------------------------------------
# Rule Document Rendering
# ---------------------------------------------------------------------------


class TestClaudeCodeAdapterRenderRuleDoc:
    def test_output_is_raw_content_without_markers(self) -> None:
        """Adapter returns plain Markdown; writer layer adds markers."""
        adapter = ClaudeCodeAdapter()
        behavior = BehaviorConfig.empty()
        result = adapter.render_rule_doc(behavior)
        assert not managed_block.has(result, path=adapter.rule_doc_path())

    def test_output_structure_with_rules(self) -> None:
        adapter = ClaudeCodeAdapter()
        behavior = BehaviorConfig(
            read=OperationRules(
                forbidden=[Rule(pattern="file:.env", reason="secrets")],
                require_approval=[],
                allow=[Rule(pattern="file:src/**")],
            ),
            write=OperationRules.empty(),
            execute=OperationRules.empty(),
        )
        result = adapter.render_rule_doc(behavior)
        # Should contain operation sections
        assert "Read" in result or "read" in result.lower()
        # Should contain forbidden rules
        assert "forbidden" in result.lower() or "Forbidden" in result

    def test_empty_behavior_produces_valid_output(self) -> None:
        adapter = ClaudeCodeAdapter()
        behavior = BehaviorConfig.empty()
        result = adapter.render_rule_doc(behavior)
        # Should still render non-empty markdown (markers added by writer)
        assert len(result) > 0
        assert not managed_block.has(result, path=adapter.rule_doc_path())


# ---------------------------------------------------------------------------
# Hook Files
# ---------------------------------------------------------------------------


class TestClaudeCodeAdapterHookFiles:
    def test_returns_hook_files(self) -> None:
        adapter = ClaudeCodeAdapter()
        behavior = BehaviorConfig.empty()
        files = adapter.hook_files(behavior)
        assert len(files) > 0

    def test_hook_file_paths(self) -> None:
        adapter = ClaudeCodeAdapter()
        behavior = BehaviorConfig.empty()
        files = adapter.hook_files(behavior)
        paths = [f.path for f in files]
        # Claude Code Hook should be under .claude/hooks/
        assert any(".claude/hooks/" in p for p in paths)

    def test_hook_files_have_content(self) -> None:
        adapter = ClaudeCodeAdapter()
        behavior = BehaviorConfig.empty()
        files = adapter.hook_files(behavior)
        for f in files:
            assert len(f.content) > 0

    def test_python_hook_is_executable(self) -> None:
        adapter = ClaudeCodeAdapter()
        behavior = BehaviorConfig.empty()
        files = adapter.hook_files(behavior)
        py_files = [f for f in files if f.path.endswith(".py")]
        for f in py_files:
            assert f.executable is True
