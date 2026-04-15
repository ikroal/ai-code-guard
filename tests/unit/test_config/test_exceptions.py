"""Tests for config exception types."""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_guard.config.exceptions import (
    ConfigError,
    ConfigFileNotFoundError,
    ConfigSyntaxError,
    ConfigValidationError,
    ValidationIssue,
)


class TestValidationIssue:
    def test_construction(self) -> None:
        issue = ValidationIssue(
            path="behavior.read.forbidden[0].pattern",
            message="required field missing",
            value=None,
        )
        assert issue.path == "behavior.read.forbidden[0].pattern"
        assert issue.message == "required field missing"
        assert issue.value is None

    def test_with_value(self) -> None:
        issue = ValidationIssue(
            path="version",
            message="expected int, got str",
            value="wrong",
        )
        assert issue.value == "wrong"

    def test_is_dataclass(self) -> None:
        issue = ValidationIssue(path="x", message="y")
        assert hasattr(issue, "__dataclass_fields__")


class TestConfigError:
    def test_is_base_class(self) -> None:
        assert issubclass(ConfigFileNotFoundError, ConfigError)
        assert issubclass(ConfigSyntaxError, ConfigError)
        assert issubclass(ConfigValidationError, ConfigError)

    def test_can_catch_broadly(self) -> None:
        with pytest.raises(ConfigError):
            raise ConfigFileNotFoundError("/missing.yaml")


class TestConfigFileNotFoundError:
    def test_path_attribute(self) -> None:
        err = ConfigFileNotFoundError("/some/path.yaml")
        assert err.path == Path("/some/path.yaml")

    def test_accepts_path_object(self) -> None:
        err = ConfigFileNotFoundError(Path("/another.yaml"))
        assert err.path == Path("/another.yaml")

    def test_message_contains_path(self) -> None:
        err = ConfigFileNotFoundError("missing.yaml")
        assert "missing.yaml" in str(err)

    def test_message_suggests_init(self) -> None:
        err = ConfigFileNotFoundError("missing.yaml")
        assert "guard init" in str(err)


class TestConfigSyntaxError:
    def test_path_attribute(self) -> None:
        err = ConfigSyntaxError("bad.yaml")
        assert err.path == Path("bad.yaml")

    def test_accepts_path_object(self) -> None:
        err = ConfigSyntaxError(Path("bad.yaml"))
        assert err.path == Path("bad.yaml")

    def test_line_column_optional(self) -> None:
        err = ConfigSyntaxError("bad.yaml", detail="some error")
        assert err.line is None
        assert err.column is None
        assert err.detail == "some error"

    def test_with_line_only(self) -> None:
        err = ConfigSyntaxError("bad.yaml", line=5, detail="oops")
        assert err.line == 5
        assert err.column is None
        assert "bad.yaml:5" in str(err)

    def test_with_line_and_column(self) -> None:
        err = ConfigSyntaxError("bad.yaml", line=10, column=3, detail="bad")
        assert err.line == 10
        assert err.column == 3
        assert "bad.yaml:10:3" in str(err)

    def test_detail_attribute(self) -> None:
        err = ConfigSyntaxError("bad.yaml", detail="unexpected token")
        assert err.detail == "unexpected token"
        assert "unexpected token" in str(err)


class TestConfigValidationError:
    def test_errors_attribute(self) -> None:
        issues = [
            ValidationIssue("version", "expected int"),
            ValidationIssue("project.language", "required"),
        ]
        err = ConfigValidationError(issues)
        assert len(err.errors) == 2
        assert err.errors[0].path == "version"

    def test_message_contains_count(self) -> None:
        issues = [ValidationIssue("x", "y")]
        err = ConfigValidationError(issues)
        assert "1 error" in str(err)

    def test_message_lists_all_paths(self) -> None:
        issues = [
            ValidationIssue("version", "bad type"),
            ValidationIssue("project.language", "missing"),
            ValidationIssue("foo", "unknown key"),
        ]
        err = ConfigValidationError(issues)
        msg = str(err)
        assert "version" in msg
        assert "project.language" in msg
        assert "foo" in msg

    def test_empty_errors_list(self) -> None:
        err = ConfigValidationError([])
        assert err.errors == []
        assert "0 error" in str(err)
