"""Tests for ac_guard.adapters.registry — built-in adapter lookup."""

from __future__ import annotations

import pytest

from ac_guard.adapters.registry import (
    _REGISTRY,
    AdapterNotFoundError,
    get_adapter,
    list_adapters,
)

# Expected closed set of built-in adapters; cross-checked against the
# snapshot suite (test_snapshots.py) that exercises render output.
_BUILTIN_NAMES = ("claude-code", "opencode", "copilot", "kilocode")


# ---------------------------------------------------------------------------
# A. Lookup
# ---------------------------------------------------------------------------


class TestGetAdapter:
    def test_returns_named_builtin(self) -> None:
        adapter = get_adapter("claude-code")
        assert adapter.name == "claude-code"
        assert adapter.capabilities.can_block is True
        assert adapter.capabilities.can_ask is True

    def test_unknown_name_raises_not_found(self) -> None:
        with pytest.raises(AdapterNotFoundError) as exc_info:
            get_adapter("does-not-exist")
        assert exc_info.value.name == "does-not-exist"
        assert set(exc_info.value.available) == set(_BUILTIN_NAMES)

    def test_returns_same_instance_each_call(self) -> None:
        # The registry holds singletons; lookup must not construct a
        # fresh adapter on each call.
        first = get_adapter("claude-code")
        second = get_adapter("claude-code")
        assert first is second


# ---------------------------------------------------------------------------
# B. Listing
# ---------------------------------------------------------------------------


class TestListAdapters:
    def test_returns_sorted_builtin_names(self) -> None:
        assert list_adapters() == sorted(_BUILTIN_NAMES)

    def test_includes_every_builtin(self) -> None:
        assert set(list_adapters()) == set(_BUILTIN_NAMES)


# ---------------------------------------------------------------------------
# C. AdapterNotFoundError
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
# D. Registry immutability — guards against accidental mutation that
#    could re-introduce the per-test cleanup discipline that the
#    legacy ``register_adapter`` / ``clear_registry`` pair forced.
# ---------------------------------------------------------------------------


class TestRegistryImmutability:
    def test_registry_rejects_item_assignment(self) -> None:
        with pytest.raises(TypeError):
            _REGISTRY["new"] = object()  # type: ignore[index]

    def test_registry_rejects_deletion(self) -> None:
        with pytest.raises(TypeError):
            del _REGISTRY["claude-code"]  # type: ignore[misc]


# ---------------------------------------------------------------------------
# E. Module exports — pin the public surface so removed symbols stay
#    removed and accidental re-exports surface as test failures.
# ---------------------------------------------------------------------------


class TestModuleExports:
    def test_registry_module_exports_only_lookup_api(self) -> None:
        from ac_guard.adapters.registry import (  # noqa: F401
            AdapterNotFoundError,
            get_adapter,
            list_adapters,
        )

    def test_no_legacy_register_or_clear_on_registry(self) -> None:
        import ac_guard.adapters.registry as registry_mod

        assert not hasattr(registry_mod, "register_adapter")
        assert not hasattr(registry_mod, "clear_registry")

    def test_no_legacy_register_or_clear_on_package(self) -> None:
        import ac_guard.adapters as adapters_pkg

        assert not hasattr(adapters_pkg, "register_adapter")
        assert not hasattr(adapters_pkg, "clear_registry")

    def test_package_all_is_exactly_the_public_surface(self) -> None:
        import ac_guard.adapters as adapters_pkg

        assert set(adapters_pkg.__all__) == {
            "AgentAdapter",
            "AgentCapabilities",
            "get_adapter",
            "list_adapters",
            "AdapterNotFoundError",
        }
