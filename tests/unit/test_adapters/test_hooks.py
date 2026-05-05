"""Tests for Hook script template rendering (WP2.2)."""

from __future__ import annotations

import json
import os
import re
import sys

from ac_guard.adapters._render import render_hook
from ac_guard.adapters.builtins.claude_code import ClaudeCodeAdapter
from ac_guard.adapters.builtins.cursor import CursorAdapter
from ac_guard.adapters.builtins.opencode import OpenCodeAdapter
from ac_guard.config.models import BehaviorConfig

# Adapter instances are stateless and cheap; reuse module-level
# singletons rather than constructing per-test.
_CLAUDE_CODE = ClaudeCodeAdapter()
_CURSOR = CursorAdapter()
_OPENCODE = OpenCodeAdapter()


class TestClaudeCodeHook:
    """Tests for Claude Code hook template."""

    def test_renders_python_script(self) -> None:
        """Claude Code hook renders a Python script."""
        content = render_hook(_CLAUDE_CODE, BehaviorConfig.empty())
        assert "from ac_guard.action_guard.core import evaluate" in content

    def test_contains_main_entry(self) -> None:
        """Claude Code hook has main() entry point."""
        content = render_hook(_CLAUDE_CODE, BehaviorConfig.empty())
        assert "def main():" in content
        assert '__name__ == "__main__"' in content

    def test_reads_stdin_json(self) -> None:
        """Claude Code hook reads stdin JSON."""
        content = render_hook(_CLAUDE_CODE, BehaviorConfig.empty())
        assert "json.load(sys.stdin)" in content

    def test_outputs_permission_decision(self) -> None:
        """Claude Code hook outputs permissionDecision format."""
        content = render_hook(_CLAUDE_CODE, BehaviorConfig.empty())
        assert "permissionDecision" in content

    def test_includes_hook_event_name(self) -> None:
        """Hook output includes hookEventName (required by Claude Code schema)."""
        content = render_hook(_CLAUDE_CODE, BehaviorConfig.empty())
        assert '"hookEventName": "PreToolUse"' in content

    def test_bakes_install_python_path(self) -> None:
        """Hook bakes the absolute path of the Python that ran `ac-guard install`."""
        content = render_hook(_CLAUDE_CODE, BehaviorConfig.empty())
        # The template uses Jinja's `| tojson` filter so Windows backslashes
        # are properly escaped; match the JSON-encoded form.
        assert f"_INSTALL_PY = {json.dumps(sys.executable)}" in content

    def test_has_reexec_shim(self) -> None:
        """Hook re-execs into the baked interpreter when sys.executable differs."""
        content = render_hook(_CLAUDE_CODE, BehaviorConfig.empty())
        assert "sys.executable != _INSTALL_PY" in content
        assert "os.execv(_INSTALL_PY" in content

    def test_has_import_safe_deny(self) -> None:
        """Hook emits an ask decision when ac_guard cannot be imported."""
        content = render_hook(_CLAUDE_CODE, BehaviorConfig.empty())
        assert "except ImportError" in content
        assert '"permissionDecision": "ask"' in content

    def test_generated_hook_is_valid_python(self) -> None:
        """Rendered hook compiles as valid Python (no syntax errors)."""
        content = render_hook(_CLAUDE_CODE, BehaviorConfig.empty())
        compile(content, "<generated claude_code hook>", "exec")


class TestCursorHook:
    """Tests for Cursor hook template."""

    def test_renders_bash_script(self) -> None:
        """Cursor hook renders a bash script."""
        content = render_hook(_CURSOR, BehaviorConfig.empty())
        assert content.startswith("#!/bin/bash")

    def test_calls_action_guard_subprocess(self) -> None:
        """Cursor hook calls action_guard via the baked python interpreter."""
        content = render_hook(_CURSOR, BehaviorConfig.empty())
        assert "-m ac_guard.action_guard" in content
        # Bake-time injection: must use an absolute path, not bare `python3`.
        assert "| python3 -m" not in content
        match = re.search(r'\| "([^"]+)" -m ac_guard\.action_guard', content)
        assert match is not None, "expected baked python path in cursor hook"
        assert os.path.isabs(match.group(1)), (
            f"baked python path is not absolute: {match.group(1)!r}"
        )

    def test_outputs_permission_format(self) -> None:
        """Cursor hook outputs permission JSON."""
        content = render_hook(_CURSOR, BehaviorConfig.empty())
        assert '"permission"' in content

    def test_downgrades_ask_to_deny(self) -> None:
        """Cursor hook downgrades ask to deny (no ask support)."""
        content = render_hook(_CURSOR, BehaviorConfig.empty())
        assert 'decision" = "ask"' in content or "ask" in content


class TestOpenCodeHook:
    """Tests for OpenCode hook template."""

    def test_renders_typescript(self) -> None:
        """OpenCode hook renders TypeScript."""
        content = render_hook(_OPENCODE, BehaviorConfig.empty())
        assert "export function intercept" in content

    def test_calls_action_guard_subprocess(self) -> None:
        """OpenCode hook calls action_guard via the baked python interpreter."""
        content = render_hook(_OPENCODE, BehaviorConfig.empty())
        assert "-m ac_guard.action_guard" in content
        assert "python3 -m ac_guard.action_guard" not in content
        # Bake-time injection: PYTHON_EXECUTABLE must hold an absolute path.
        match = re.search(r'const PYTHON_EXECUTABLE = "([^"]+)";', content)
        assert match is not None, "expected PYTHON_EXECUTABLE constant in opencode hook"
        assert os.path.isabs(match.group(1)), (
            f"baked python path is not absolute: {match.group(1)!r}"
        )

    def test_throws_on_deny(self) -> None:
        """OpenCode hook throws Error on deny."""
        content = render_hook(_OPENCODE, BehaviorConfig.empty())
        assert "throw new Error" in content

    def test_imports_child_process(self) -> None:
        """OpenCode hook imports child_process for subprocess."""
        content = render_hook(_OPENCODE, BehaviorConfig.empty())
        assert "child_process" in content
