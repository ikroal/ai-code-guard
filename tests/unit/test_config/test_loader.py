"""Tests for config loader."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from ai_guard.config.exceptions import (
    ConfigFileNotFoundError,
    ConfigSyntaxError,
    ConfigValidationError,
)
from ai_guard.config.loader import load_config


def _write_yaml(tmp_path: Path, data: dict) -> Path:
    """Dump *data* as YAML into a temporary file and return its path."""
    p = tmp_path / "guard.yaml"
    p.write_text(yaml.dump(data, default_flow_style=False), encoding="utf-8")
    return p


def _write_text(tmp_path: Path, text: str) -> Path:
    """Write raw *text* into a temporary file and return its path."""
    p = tmp_path / "guard.yaml"
    p.write_text(text, encoding="utf-8")
    return p


class TestLoadConfigSuccess:
    def test_minimal_config(self, tmp_path: Path) -> None:
        path = _write_yaml(tmp_path, {"version": 1, "project": {"language": "python"}})
        result = load_config(path)
        assert isinstance(result, dict)
        assert result["version"] == 1
        assert result["project"]["language"] == "python"

    def test_full_config(self, tmp_path: Path) -> None:
        data = {
            "version": 1,
            "project": {"name": "test", "language": "python"},
            "rulesets": ["git@github.com:co/rules.git"],
            "languages": {
                "python": {"tools": {"format": "black", "lint": "ruff"}},
            },
            "behavior": {
                "read": {
                    "forbidden": [
                        {"pattern": "file:**/token.*", "reason": "secrets"},
                    ],
                },
                "write": {
                    "allow": [{"pattern": "file:scripts/**"}],
                    "remove": [{"pattern": "file:build/**"}],
                },
            },
            "code": {
                "commit": {
                    "format": True,
                    "checks": {
                        "lic": {"command": "./check-lic.sh"},
                    },
                },
            },
            "build": {"command": "make"},
            "output": {"verbosity": "verbose", "locale": "zh-CN"},
        }
        path = _write_yaml(tmp_path, data)
        result = load_config(path)
        assert result["project"]["name"] == "test"
        assert result["behavior"]["write"]["remove"] == [{"pattern": "file:build/**"}]

    def test_returns_dict_not_dataclass(self, tmp_path: Path) -> None:
        path = _write_yaml(tmp_path, {"version": 1, "project": {"language": "go"}})
        result = load_config(path)
        assert isinstance(result, dict)
        assert result.__class__ is dict

    def test_accepts_string_path(self, tmp_path: Path) -> None:
        path = _write_yaml(tmp_path, {"version": 1, "project": {"language": "rust"}})
        result = load_config(str(path))
        assert result["project"]["language"] == "rust"

    def test_preserves_remove_entries(self, tmp_path: Path) -> None:
        data = {
            "version": 1,
            "project": {"language": "python"},
            "behavior": {
                "write": {
                    "remove": [{"pattern": "file:build/**"}],
                },
            },
        }
        path = _write_yaml(tmp_path, data)
        result = load_config(path)
        assert len(result["behavior"]["write"]["remove"]) == 1


class TestLoadConfigFileNotFound:
    def test_missing_file(self, tmp_path: Path) -> None:
        path = tmp_path / "nonexistent.yaml"
        with pytest.raises(ConfigFileNotFoundError) as exc_info:
            load_config(path)
        assert "nonexistent.yaml" in str(exc_info.value)
        assert "guard init" in str(exc_info.value)

    def test_error_has_path_attribute(self, tmp_path: Path) -> None:
        path = tmp_path / "missing.yaml"
        with pytest.raises(ConfigFileNotFoundError) as exc_info:
            load_config(path)
        assert exc_info.value.path == path


class TestLoadConfigSyntaxError:
    def test_malformed_yaml(self, tmp_path: Path) -> None:
        path = _write_text(tmp_path, "key: [unclosed\n")
        with pytest.raises(ConfigSyntaxError) as exc_info:
            load_config(path)
        assert exc_info.value.path == path

    def test_syntax_error_has_line(self, tmp_path: Path) -> None:
        path = _write_text(tmp_path, "valid: true\nbad: [unclosed\n")
        with pytest.raises(ConfigSyntaxError) as exc_info:
            load_config(path)
        assert exc_info.value.line is not None

    def test_tab_indentation_error(self, tmp_path: Path) -> None:
        path = _write_text(tmp_path, "key:\n\tvalue: true\n")
        with pytest.raises(ConfigSyntaxError):
            load_config(path)


class TestLoadConfigValidationError:
    def test_empty_file(self, tmp_path: Path) -> None:
        path = _write_text(tmp_path, "")
        with pytest.raises(ConfigValidationError):
            load_config(path)

    def test_yaml_list_not_dict(self, tmp_path: Path) -> None:
        path = _write_text(tmp_path, "- item1\n- item2\n")
        with pytest.raises(ConfigValidationError):
            load_config(path)

    def test_schema_violation_propagated(self, tmp_path: Path) -> None:
        path = _write_yaml(
            tmp_path, {"version": "bad", "project": {"language": "python"}}
        )
        with pytest.raises(ConfigValidationError) as exc_info:
            load_config(path)
        assert any("version" in e.path for e in exc_info.value.errors)
