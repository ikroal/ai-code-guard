"""Tests for ai_guard.adapters.base — AgentAdapter ABC and AgentCapabilities."""

from __future__ import annotations

import pytest

from ai_guard.adapters.base import AgentAdapter, AgentCapabilities
from ai_guard.config.models import BehaviorConfig
from ai_guard.shared.types import FileSpec

# ---------------------------------------------------------------------------
# A. AgentCapabilities
# ---------------------------------------------------------------------------


class TestAgentCapabilities:
    def test_construction(self) -> None:
        caps = AgentCapabilities(can_block=True, can_ask=True)
        assert caps.can_block is True
        assert caps.can_ask is True

    def test_frozen(self) -> None:
        caps = AgentCapabilities(can_block=True, can_ask=False)
        with pytest.raises(AttributeError):
            caps.can_block = False  # type: ignore[misc]

    def test_both_false(self) -> None:
        caps = AgentCapabilities(can_block=False, can_ask=False)
        assert caps.can_block is False
        assert caps.can_ask is False

    def test_mixed(self) -> None:
        caps = AgentCapabilities(can_block=True, can_ask=False)
        assert caps.can_block is True
        assert caps.can_ask is False


# ---------------------------------------------------------------------------
# B. AgentAdapter ABC
# ---------------------------------------------------------------------------


class TestAgentAdapterABC:
    def test_cannot_instantiate_directly(self) -> None:
        # AgentAdapter is abstract, cannot instantiate
        with pytest.raises(TypeError):
            AgentAdapter()  # type: ignore[abstract]

    def test_subclass_must_implement_all(self) -> None:
        # Missing implementations should raise TypeError
        class IncompleteAdapter(AgentAdapter):
            @property
            def name(self) -> str:
                return "incomplete"

            # Missing: capabilities, rule_doc_path, render_rule_doc, hook_files

        with pytest.raises(TypeError):
            IncompleteAdapter()  # type: ignore[abstract]

    def test_complete_subclass_can_instantiate(self) -> None:
        class CompleteAdapter(AgentAdapter):
            @property
            def name(self) -> str:
                return "complete"

            @property
            def capabilities(self) -> AgentCapabilities:
                return AgentCapabilities(can_block=True, can_ask=True)

            def rule_doc_path(self) -> str:
                return "RULES.md"

            def render_rule_doc(self, behavior: BehaviorConfig) -> str:
                return "content"

            def hook_files(self, behavior: BehaviorConfig) -> list[FileSpec]:
                return []

        adapter = CompleteAdapter()
        assert adapter.name == "complete"
        assert adapter.capabilities.can_block is True
        assert adapter.rule_doc_path() == "RULES.md"

    def test_render_rule_doc_signature(self) -> None:
        # Verify method signature accepts BehaviorConfig
        class TestAdapter(AgentAdapter):
            @property
            def name(self) -> str:
                return "test"

            @property
            def capabilities(self) -> AgentCapabilities:
                return AgentCapabilities(can_block=False, can_ask=False)

            def rule_doc_path(self) -> str:
                return "test.md"

            def render_rule_doc(self, behavior: BehaviorConfig) -> str:
                # Should be able to access behavior fields
                assert isinstance(behavior, BehaviorConfig)
                return f"read forbidden: {len(behavior.read.forbidden)}"

            def hook_files(self, behavior: BehaviorConfig) -> list[FileSpec]:
                return []

        adapter = TestAdapter()
        behavior = BehaviorConfig.empty()
        result = adapter.render_rule_doc(behavior)
        assert "read forbidden: 0" in result

    def test_hook_files_returns_filespec_list(self) -> None:
        class TestAdapter(AgentAdapter):
            @property
            def name(self) -> str:
                return "test"

            @property
            def capabilities(self) -> AgentCapabilities:
                return AgentCapabilities(can_block=True, can_ask=True)

            def rule_doc_path(self) -> str:
                return "test.md"

            def render_rule_doc(self, behavior: BehaviorConfig) -> str:
                return "content"

            def hook_files(self, behavior: BehaviorConfig) -> list[FileSpec]:
                return [
                    FileSpec(path=".hooks/test.py", content="# test", executable=True),
                ]

        adapter = TestAdapter()
        files = adapter.hook_files(BehaviorConfig.empty())
        assert len(files) == 1
        assert files[0].path == ".hooks/test.py"
        assert files[0].executable is True


# ---------------------------------------------------------------------------
# C. Module exports
# ---------------------------------------------------------------------------


class TestModuleExports:
    def test_base_exports(self) -> None:
        from ai_guard.adapters.base import (  # noqa: F401
            AgentAdapter,
            AgentCapabilities,
        )

    def test_all_list(self) -> None:
        import ai_guard.adapters.base as base

        assert set(base.__all__) == {
            "AgentAdapter",
            "AgentCapabilities",
        }
