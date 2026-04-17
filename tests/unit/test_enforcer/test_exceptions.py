"""Tests for Enforcer exception types."""

from __future__ import annotations

from ac_guard.enforcer.exceptions import EnforcerError, PolicyCorruptError


class TestPolicyCorruptError:
    """Tests for PolicyCorruptError."""

    def test_inherits_enforcer_error(self) -> None:
        """PolicyCorruptError is an EnforcerError."""
        err = PolicyCorruptError("/path/policy.json", "bad json")
        assert isinstance(err, EnforcerError)

    def test_attributes(self) -> None:
        """PolicyCorruptError stores path and detail."""
        err = PolicyCorruptError("/path/policy.json", "parse error")
        assert err.path == "/path/policy.json"
        assert err.detail == "parse error"

    def test_str_contains_path(self) -> None:
        """String representation contains the file path."""
        err = PolicyCorruptError("/path/policy.json")
        assert "/path/policy.json" in str(err)


class TestEnforcerError:
    """Tests for EnforcerError base class."""

    def test_is_exception(self) -> None:
        """EnforcerError is an Exception."""
        assert issubclass(EnforcerError, Exception)
