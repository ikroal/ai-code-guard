"""Tests for Action guard exception types."""

from __future__ import annotations

from ac_guard.action_guard.exceptions import ActionGuardError, PolicyCorruptError


class TestPolicyCorruptError:
    """Tests for PolicyCorruptError."""

    def test_inherits_action_guard_error(self) -> None:
        """PolicyCorruptError is an ActionGuardError."""
        err = PolicyCorruptError("/path/runtime.json", "bad json")
        assert isinstance(err, ActionGuardError)

    def test_attributes(self) -> None:
        """PolicyCorruptError stores path and detail."""
        err = PolicyCorruptError("/path/runtime.json", "parse error")
        assert err.path == "/path/runtime.json"
        assert err.detail == "parse error"

    def test_str_contains_path(self) -> None:
        """String representation contains the file path."""
        err = PolicyCorruptError("/path/runtime.json")
        assert "/path/runtime.json" in str(err)


class TestActionGuardError:
    """Tests for ActionGuardError base class."""

    def test_is_exception(self) -> None:
        """ActionGuardError is an Exception."""
        assert issubclass(ActionGuardError, Exception)
