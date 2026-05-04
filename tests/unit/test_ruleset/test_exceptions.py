"""Tests for ruleset exception types."""

from __future__ import annotations

from ac_guard.ruleset import (
    RulesetError,
    RulesetFetchError,
    RulesetURLError,
    RulesetValidationError,
)


class TestRulesetExceptionHierarchy:
    """Verify exception inheritance and message formatting."""

    def test_base_is_exception(self) -> None:
        assert issubclass(RulesetError, Exception)

    def test_url_error_inherits(self) -> None:
        assert issubclass(RulesetURLError, RulesetError)

    def test_fetch_error_inherits(self) -> None:
        assert issubclass(RulesetFetchError, RulesetError)

    def test_validation_error_inherits(self) -> None:
        assert issubclass(RulesetValidationError, RulesetError)


class TestRulesetURLError:
    """Test RulesetURLError message formatting."""

    def test_message_without_detail(self) -> None:
        err = RulesetURLError("bad-url")
        assert "bad-url" in str(err)
        assert err.raw == "bad-url"

    def test_message_with_detail(self) -> None:
        err = RulesetURLError("bad-url", "empty URL")
        assert "empty URL" in str(err)


class TestRulesetFetchError:
    """Test RulesetFetchError message formatting."""

    def test_message_without_stderr(self) -> None:
        err = RulesetFetchError("https://example.com/repo.git")
        assert "example.com" in str(err)
        assert err.url == "https://example.com/repo.git"

    def test_message_with_stderr(self) -> None:
        err = RulesetFetchError("url", "fatal: not found")
        assert "fatal: not found" in str(err)
        assert err.stderr == "fatal: not found"


class TestRulesetValidationError:
    """Test RulesetValidationError message formatting."""

    def test_message_without_detail(self) -> None:
        err = RulesetValidationError("my-rules")
        assert "my-rules" in str(err)
        assert err.name == "my-rules"

    def test_message_with_detail(self) -> None:
        err = RulesetValidationError("my-rules", "guard.yaml not found")
        assert "guard.yaml not found" in str(err)
