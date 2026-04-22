"""Tests for ac_guard.adapters.registry — Adapter registration and lookup."""

from __future__ import annotations

import pytest

from ac_guard.adapters.base import AgentAdapter, AgentCapabilities
from ac_guard.adapters.registry import (
    AdapterNotFoundError,
    clear_registry,
    get_adapter,
    list_adapters,
    register_adapter,
)
from ac_guard.config.models import BehaviorConfig
from ac_guard.domain import FileSpec


# Helper to create minimal adapter for testing
class _MockAdapter(AgentAdapter):
    def __init__(self, name: str, can_block: bool = True, can_ask: bool = True) -> None:
        self._name = name
        self._caps = AgentCapabilities(can_block=can_block, can_ask=can_ask)

    @property
    def name(self) -> str:
        return self._name

    @property
    def capabilities(self) -> AgentCapabilities:
        return self._caps

    def rule_doc_path(self) -> str:
        return f"{self._name}.md"

    def render_rule_doc(self, behavior: BehaviorConfig) -> str:
        return "mock content"

    def hook_files(self, behavior: BehaviorConfig) -> list[FileSpec]:
        return []


# ---------------------------------------------------------------------------
# A. Registration
# ---------------------------------------------------------------------------


class TestRegisterAdapter:
    def test_register_new_adapter(self) -> None:
        clear_registry()
        adapter = _MockAdapter("test-agent")
        register_adapter(adapter)
        assert "test-agent" in list_adapters()

    def test_register_duplicate_raises(self) -> None:
        clear_registry()
        adapter1 = _MockAdapter("duplicate")
        adapter2 = _MockAdapter("duplicate")
        register_adapter(adapter1)
        with pytest.raises(ValueError, match="already registered"):
            register_adapter(adapter2)

    def test_register_multiple_different(self) -> None:
        clear_registry()
        register_adapter(_MockAdapter("agent-a"))
        register_adapter(_MockAdapter("agent-b"))
        register_adapter(_MockAdapter("agent-c"))
        adapters = list_adapters()
        assert len(adapters) == 3
        assert "agent-a" in adapters
        assert "agent-b" in adapters
        assert "agent-c" in adapters


# ---------------------------------------------------------------------------
# B. Lookup
# ---------------------------------------------------------------------------


class TestGetAdapter:
    def test_get_registered_adapter(self) -> None:
        clear_registry()
        adapter = _MockAdapter("found")
        register_adapter(adapter)
        result = get_adapter("found")
        assert result is adapter
        assert result.name == "found"

    def test_get_unregistered_raises_not_found(self) -> None:
        clear_registry()
        with pytest.raises(AdapterNotFoundError) as exc_info:
            get_adapter("missing")
        assert exc_info.value.name == "missing"
        assert exc_info.value.available == []

    def test_error_message_includes_available(self) -> None:
        clear_registry()
        register_adapter(_MockAdapter("a"))
        register_adapter(_MockAdapter("b"))
        with pytest.raises(AdapterNotFoundError) as exc_info:
            get_adapter("missing")
        assert "a" in str(exc_info.value)
        assert "b" in str(exc_info.value)


# ---------------------------------------------------------------------------
# C. List
# ---------------------------------------------------------------------------


class TestListAdapters:
    def test_empty_registry(self) -> None:
        clear_registry()
        assert list_adapters() == []

    def test_returns_sorted_list(self) -> None:
        clear_registry()
        register_adapter(_MockAdapter("z-agent"))
        register_adapter(_MockAdapter("a-agent"))
        register_adapter(_MockAdapter("m-agent"))
        result = list_adapters()
        assert result == ["a-agent", "m-agent", "z-agent"]

    def test_list_after_clear(self) -> None:
        clear_registry()
        register_adapter(_MockAdapter("x"))
        assert "x" in list_adapters()
        clear_registry()
        assert list_adapters() == []


# ---------------------------------------------------------------------------
# D. Clear Registry
# ---------------------------------------------------------------------------


class TestClearRegistry:
    def test_clear_removes_all(self) -> None:
        clear_registry()
        register_adapter(_MockAdapter("a"))
        register_adapter(_MockAdapter("b"))
        clear_registry()
        assert list_adapters() == []

    def test_clear_on_empty_is_safe(self) -> None:
        clear_registry()
        clear_registry()  # Should not raise
        assert list_adapters() == []


# ---------------------------------------------------------------------------
# E. AdapterNotFoundError
# ---------------------------------------------------------------------------


class TestAdapterNotFoundError:
    def test_attributes(self) -> None:
        err = AdapterNotFoundError("unknown", ["a", "b"])
        assert err.name == "unknown"
        assert err.available == ["a", "b"]

    def test_message_format(self) -> None:
        err = AdapterNotFoundError("unknown", ["a", "b"])
        msg = str(err)
        assert "unknown" in msg
        assert "a, b" in msg


# ---------------------------------------------------------------------------
# F. Built-in Registration
# ---------------------------------------------------------------------------


class TestBuiltinRegistration:
    def test_builtins_registered_on_import(self) -> None:
        # This test assumes builtins are auto-registered
        # We need to re-import to trigger registration after clear
        clear_registry()
        # Re-import registry module to trigger _register_builtins
        import importlib

        import ac_guard.adapters.registry as registry_mod

        importlib.reload(registry_mod)

        adapters = list_adapters()
        assert "claude-code" in adapters
        assert "cursor" in adapters
        assert "opencode" in adapters
        assert "copilot" in adapters
        assert "kilocode" in adapters

    def test_get_builtin_claude_code(self) -> None:
        clear_registry()
        import importlib

        import ac_guard.adapters.registry as registry_mod

        importlib.reload(registry_mod)

        adapter = get_adapter("claude-code")
        assert adapter.name == "claude-code"
        assert adapter.capabilities.can_block is True
        assert adapter.capabilities.can_ask is True


# ---------------------------------------------------------------------------
# G. Module exports
# ---------------------------------------------------------------------------


class TestModuleExports:
    def test_registry_exports(self) -> None:
        from ac_guard.adapters.registry import (  # noqa: F401
            AdapterNotFoundError,
            clear_registry,
            get_adapter,
            list_adapters,
            register_adapter,
        )
