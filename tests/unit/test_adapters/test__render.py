"""Tests for ai_guard.adapters._render — Shared rendering utilities."""

from __future__ import annotations

from pathlib import Path

from ai_guard.adapters._render import get_template_dir, render_hook, render_rule_doc
from ai_guard.config.models import BehaviorConfig, OperationRules, Rule
from ai_guard.shared.types import MARKER_BEGIN, MARKER_END


class TestGetTemplateDir:
    """get_template_dir function tests."""

    def test_returns_path(self) -> None:
        result = get_template_dir()
        assert isinstance(result, Path)
        assert result.name == "_templates"

    def test_template_dir_exists(self) -> None:
        result = get_template_dir()
        assert result.is_dir()


class TestRenderRuleDoc:
    """render_rule_doc function tests."""

    def test_claude_code_template_exists(self) -> None:
        behavior = BehaviorConfig.empty()
        result = render_rule_doc("claude_code", behavior)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_cursor_template_exists(self) -> None:
        behavior = BehaviorConfig.empty()
        result = render_rule_doc("cursor", behavior)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_cursor_has_frontmatter(self) -> None:
        behavior = BehaviorConfig.empty()
        result = render_rule_doc("cursor", behavior)
        assert "---" in result
        assert "globs:" in result

    def test_opencode_template_exists(self) -> None:
        behavior = BehaviorConfig.empty()
        result = render_rule_doc("opencode", behavior)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_copilot_template_has_warning(self) -> None:
        behavior = BehaviorConfig.empty()
        result = render_rule_doc("copilot", behavior)
        assert "Warning" in result or "warning" in result.lower()
        assert "soft constraints" in result.lower()

    def test_kilocode_template_has_warning(self) -> None:
        behavior = BehaviorConfig.empty()
        result = render_rule_doc("kilocode", behavior)
        assert "Warning" in result or "warning" in result.lower()
        assert "soft constraints" in result.lower()

    def test_contains_rules(self) -> None:
        behavior = BehaviorConfig(
            read=OperationRules(
                forbidden=[Rule(pattern="file:.env", reason="secrets")],
                require_approval=[],
                allow=[],
            ),
            write=OperationRules.empty(),
            execute=OperationRules.empty(),
        )
        result = render_rule_doc("claude_code", behavior)
        assert "file:.env" in result
        assert "secrets" in result

    def test_no_markers_in_output(self) -> None:
        # render_rule_doc returns content without managed block markers
        # The caller (adapter) wraps it
        behavior = BehaviorConfig.empty()
        result = render_rule_doc("claude_code", behavior)
        assert MARKER_BEGIN not in result
        assert MARKER_END not in result


class TestRenderHook:
    """render_hook function tests."""

    def test_claude_code_hook_exists(self) -> None:
        behavior = BehaviorConfig.empty()
        result = render_hook("claude_code", behavior)
        assert isinstance(result, str)
        assert len(result) > 0
        assert "import json" in result  # Python script

    def test_cursor_hook_exists(self) -> None:
        behavior = BehaviorConfig.empty()
        result = render_hook("cursor", behavior)
        assert isinstance(result, str)
        assert len(result) > 0
        assert "#!/bin/bash" in result  # Shell script

    def test_opencode_hook_exists(self) -> None:
        behavior = BehaviorConfig.empty()
        result = render_hook("opencode", behavior)
        assert isinstance(result, str)
        assert len(result) > 0
        assert "export function intercept" in result  # TypeScript module

    def test_claude_code_hook_is_python(self) -> None:
        behavior = BehaviorConfig.empty()
        result = render_hook("claude_code", behavior)
        assert "def main()" in result
        assert "sys.stdin" in result

    def test_cursor_hook_is_shell(self) -> None:
        behavior = BehaviorConfig.empty()
        result = render_hook("cursor", behavior)
        assert "input=$(cat)" in result
        assert "jq" in result

    def test_opencode_hook_is_typescript(self) -> None:
        behavior = BehaviorConfig.empty()
        result = render_hook("opencode", behavior)
        assert "intercept" in result
        assert "ToolCall" in result
