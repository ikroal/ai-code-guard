"""Tests for Hook script template rendering (WP2.2)."""

from __future__ import annotations

import json
import os
import re
import sys

from ac_guard.adapters._render import render_hook
from ac_guard.adapters.builtins.claude_code import ClaudeCodeAdapter
from ac_guard.adapters.builtins.codex import CodexAdapter
from ac_guard.adapters.builtins.copilot import CopilotAdapter
from ac_guard.adapters.builtins.opencode import OpenCodeAdapter
from ac_guard.config.models import BehaviorConfig

# Adapter instances are stateless and cheap; reuse module-level
# singletons rather than constructing per-test.
_CLAUDE_CODE = ClaudeCodeAdapter()
_CODEX = CodexAdapter()
_COPILOT = CopilotAdapter()
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


class TestCodexHook:
    """Tests for Codex hook template."""

    def test_renders_python_script(self) -> None:
        """Codex hook renders a Python script."""
        content = render_hook(_CODEX, BehaviorConfig.empty())
        assert "from ac_guard.action_guard.core import evaluate" in content

    def test_contains_main_entry(self) -> None:
        """Codex hook has main() entry point."""
        content = render_hook(_CODEX, BehaviorConfig.empty())
        assert "def main():" in content
        assert '__name__ == "__main__"' in content

    def test_reads_stdin_json(self) -> None:
        """Codex hook reads stdin JSON."""
        content = render_hook(_CODEX, BehaviorConfig.empty())
        assert "json.load(sys.stdin)" in content

    def test_outputs_permission_decision(self) -> None:
        """Codex hook outputs permissionDecision format."""
        content = render_hook(_CODEX, BehaviorConfig.empty())
        assert "permissionDecision" in content

    def test_includes_hook_event_name(self) -> None:
        """Hook output includes hookEventName (required by Codex schema)."""
        content = render_hook(_CODEX, BehaviorConfig.empty())
        assert '"hookEventName": "PreToolUse"' in content

    def test_bakes_install_python_path(self) -> None:
        """Hook bakes the absolute path of the Python that ran `ac-guard install`."""
        content = render_hook(_CODEX, BehaviorConfig.empty())
        assert f"_INSTALL_PY = {json.dumps(sys.executable)}" in content

    def test_has_reexec_shim(self) -> None:
        """Hook re-execs into the baked interpreter when sys.executable differs."""
        content = render_hook(_CODEX, BehaviorConfig.empty())
        assert "sys.executable != _INSTALL_PY" in content
        assert "os.execv(_INSTALL_PY" in content

    def test_has_import_safe_deny(self) -> None:
        """Hook emits a deny decision when ac_guard cannot be imported."""
        content = render_hook(_CODEX, BehaviorConfig.empty())
        assert "except ImportError" in content
        assert '"permissionDecision": "deny"' in content

    def test_generated_hook_is_valid_python(self) -> None:
        """Rendered hook compiles as valid Python (no syntax errors)."""
        content = render_hook(_CODEX, BehaviorConfig.empty())
        # Only the Python part after "--- SPLIT ---"
        python_part = content.split("--- SPLIT ---\n")[1]
        compile(python_part, "<generated codex hook>", "exec")

    def test_contains_hooks_json_config(self) -> None:
        """Rendered template contains hooks.json configuration."""
        content = render_hook(_CODEX, BehaviorConfig.empty())
        json_part = content.split("--- SPLIT ---\n")[0]
        assert '"hooks"' in json_part
        assert '"PreToolUse"' in json_part


class TestCopilotHook:
    """Tests for Copilot hook template."""

    def test_renders_python_script(self) -> None:
        """Copilot hook renders a Python script."""
        content = render_hook(_COPILOT, BehaviorConfig.empty())
        assert "from ac_guard.action_guard.core import evaluate" in content

    def test_contains_main_entry(self) -> None:
        """Copilot hook has main() entry point."""
        content = render_hook(_COPILOT, BehaviorConfig.empty())
        assert "def main():" in content
        assert '__name__ == "__main__"' in content

    def test_reads_stdin_json(self) -> None:
        """Copilot hook reads stdin JSON."""
        content = render_hook(_COPILOT, BehaviorConfig.empty())
        assert "json.load(sys.stdin)" in content

    def test_outputs_permission_decision(self) -> None:
        """Copilot hook outputs permissionDecision format."""
        content = render_hook(_COPILOT, BehaviorConfig.empty())
        assert "permissionDecision" in content

    def test_includes_hook_event_name(self) -> None:
        """Hook output includes hookEventName for Copilot."""
        content = render_hook(_COPILOT, BehaviorConfig.empty())
        assert '"hookEventName": "onPreToolUse"' in content

    def test_bakes_install_python_path(self) -> None:
        """Hook bakes the absolute path of the Python that ran `ac-guard install`."""
        content = render_hook(_COPILOT, BehaviorConfig.empty())
        assert f"_INSTALL_PY = {json.dumps(sys.executable)}" in content

    def test_has_reexec_shim(self) -> None:
        """Hook re-execs into the baked interpreter when sys.executable differs."""
        content = render_hook(_COPILOT, BehaviorConfig.empty())
        assert "sys.executable != _INSTALL_PY" in content
        assert "os.execv(_INSTALL_PY" in content

    def test_has_import_safe_deny(self) -> None:
        """Hook emits a deny decision when ac_guard cannot be imported."""
        content = render_hook(_COPILOT, BehaviorConfig.empty())
        assert "except ImportError" in content
        assert '"permissionDecision": "deny"' in content

    def test_generated_hook_is_valid_python(self) -> None:
        """Rendered hook compiles as valid Python (no syntax errors)."""
        content = render_hook(_COPILOT, BehaviorConfig.empty())
        compile(content, "<generated copilot hook>", "exec")
