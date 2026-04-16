"""Tests for Hook script template rendering (WP2.2)."""

from __future__ import annotations

from ai_guard.adapters._render import render_hook
from ai_guard.config.models import BehaviorConfig


class TestClaudeCodeHook:
    """Tests for Claude Code hook template."""

    def test_renders_python_script(self) -> None:
        """Claude Code hook renders a Python script."""
        content = render_hook("claude_code", BehaviorConfig.empty())
        assert "from ai_guard.enforcer.engine import evaluate" in content

    def test_contains_main_entry(self) -> None:
        """Claude Code hook has main() entry point."""
        content = render_hook("claude_code", BehaviorConfig.empty())
        assert "def main():" in content
        assert '__name__ == "__main__"' in content

    def test_reads_stdin_json(self) -> None:
        """Claude Code hook reads stdin JSON."""
        content = render_hook("claude_code", BehaviorConfig.empty())
        assert "json.load(sys.stdin)" in content

    def test_outputs_permission_decision(self) -> None:
        """Claude Code hook outputs permissionDecision format."""
        content = render_hook("claude_code", BehaviorConfig.empty())
        assert "permissionDecision" in content


class TestCursorHook:
    """Tests for Cursor hook template."""

    def test_renders_bash_script(self) -> None:
        """Cursor hook renders a bash script."""
        content = render_hook("cursor", BehaviorConfig.empty())
        assert content.startswith("#!/bin/bash")

    def test_calls_enforcer_subprocess(self) -> None:
        """Cursor hook calls Python enforcer via subprocess."""
        content = render_hook("cursor", BehaviorConfig.empty())
        assert "python3 -m ai_guard.enforcer" in content

    def test_outputs_permission_format(self) -> None:
        """Cursor hook outputs permission JSON."""
        content = render_hook("cursor", BehaviorConfig.empty())
        assert '"permission"' in content

    def test_downgrades_ask_to_deny(self) -> None:
        """Cursor hook downgrades ask to deny (no ask support)."""
        content = render_hook("cursor", BehaviorConfig.empty())
        assert 'decision" = "ask"' in content or "ask" in content


class TestOpenCodeHook:
    """Tests for OpenCode hook template."""

    def test_renders_typescript(self) -> None:
        """OpenCode hook renders TypeScript."""
        content = render_hook("opencode", BehaviorConfig.empty())
        assert "export function intercept" in content

    def test_calls_enforcer_subprocess(self) -> None:
        """OpenCode hook calls Python enforcer via subprocess."""
        content = render_hook("opencode", BehaviorConfig.empty())
        assert "python3 -m ai_guard.enforcer" in content

    def test_throws_on_deny(self) -> None:
        """OpenCode hook throws Error on deny."""
        content = render_hook("opencode", BehaviorConfig.empty())
        assert "throw new Error" in content

    def test_imports_child_process(self) -> None:
        """OpenCode hook imports child_process for subprocess."""
        content = render_hook("opencode", BehaviorConfig.empty())
        assert "child_process" in content
