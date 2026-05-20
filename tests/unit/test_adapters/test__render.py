"""Tests for ac_guard.adapters._render — Shared rendering utilities."""

from __future__ import annotations

from ac_guard.adapters._render import _TEMPLATE_DIR, render_hook, render_rule_doc
from ac_guard.adapters.builtins.claude_code import ClaudeCodeAdapter
from ac_guard.adapters.builtins.codex import CodexAdapter
from ac_guard.adapters.builtins.copilot import CopilotAdapter
from ac_guard.adapters.builtins.kilocode import KiloCodeAdapter
from ac_guard.adapters.builtins.opencode import OpenCodeAdapter
from ac_guard.config.models import BehaviorConfig, OperationRules, Rule
from ac_guard.domain import managed_block

_CLAUDE_CODE = ClaudeCodeAdapter()
_CODEX = CodexAdapter()
_OPENCODE = OpenCodeAdapter()
_COPILOT = CopilotAdapter()
_KILOCODE = KiloCodeAdapter()


class TestRenderRuleDoc:
    """render_rule_doc function tests."""

    def test_claude_code_template_exists(self) -> None:
        behavior = BehaviorConfig.empty()
        result = render_rule_doc(_CLAUDE_CODE, behavior)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_opencode_template_exists(self) -> None:
        behavior = BehaviorConfig.empty()
        result = render_rule_doc(_OPENCODE, behavior)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_copilot_template_uses_base(self) -> None:
        """Copilot now has hook capability and uses the base template."""
        behavior = BehaviorConfig.empty()
        result = render_rule_doc(_COPILOT, behavior)
        assert "Behavior Constraints" in result
        # No longer has soft-constraint warning
        assert "soft constraints" not in result.lower()

    def test_kilocode_template_has_warning(self) -> None:
        behavior = BehaviorConfig.empty()
        result = render_rule_doc(_KILOCODE, behavior)
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
        result = render_rule_doc(_CLAUDE_CODE, behavior)
        assert "file:.env" in result
        assert "secrets" in result

    def test_no_markers_in_output(self) -> None:
        # render_rule_doc returns content without managed block markers;
        # the writer layer (managed_block.wrap / managed_block.replace) wraps it.
        behavior = BehaviorConfig.empty()
        result = render_rule_doc(_CLAUDE_CODE, behavior)
        assert not managed_block.has(result, path="CLAUDE.md")


class TestRenderHook:
    """render_hook function tests."""

    def test_claude_code_hook_exists(self) -> None:
        behavior = BehaviorConfig.empty()
        result = render_hook(_CLAUDE_CODE, behavior)
        assert isinstance(result, str)
        assert len(result) > 0
        assert "import json" in result  # Python script

    def test_opencode_hook_exists(self) -> None:
        behavior = BehaviorConfig.empty()
        result = render_hook(_OPENCODE, behavior)
        assert isinstance(result, str)
        assert len(result) > 0
        assert "export function intercept" in result  # TypeScript module

    def test_claude_code_hook_is_python(self) -> None:
        behavior = BehaviorConfig.empty()
        result = render_hook(_CLAUDE_CODE, behavior)
        assert "def main()" in result
        assert "sys.stdin" in result

    def test_opencode_hook_is_typescript(self) -> None:
        behavior = BehaviorConfig.empty()
        result = render_hook(_OPENCODE, behavior)
        assert "intercept" in result
        assert "ToolCall" in result


class TestTemplateStems:
    """_template_stem ↔ _templates/ filesystem layout invariant.

    Adding a new builtin adapter without colocating its templates
    would surface here rather than at first install.
    """

    def test_rule_doc_template_exists_for_each_builtin(self) -> None:
        adapters = [_CLAUDE_CODE, _CODEX, _OPENCODE, _COPILOT, _KILOCODE]
        rule_doc_dir = _TEMPLATE_DIR / "rule_docs"
        for adapter in adapters:
            template = rule_doc_dir / f"{adapter._template_stem}.md.j2"
            assert template.is_file(), (
                f"Missing rule_doc template for {adapter.name}: {template}"
            )

    def test_hook_template_exists_for_each_block_capable_builtin(self) -> None:
        # Only adapters with can_block=True render hook scripts.
        block_capable = [_CLAUDE_CODE, _CODEX, _OPENCODE, _COPILOT]
        hook_dir = _TEMPLATE_DIR / "hooks"
        for adapter in block_capable:
            template = hook_dir / f"{adapter._template_stem}.j2"
            assert template.is_file(), (
                f"Missing hook template for {adapter.name}: {template}"
            )
