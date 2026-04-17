"""Tests for validation list and report commands."""

from __future__ import annotations

from pathlib import Path

import yaml
from typer.testing import CliRunner

from ac_guard.cli.main import app

runner = CliRunner()


def _write_config(tmp_path: Path, *, custom_checks: bool = False) -> Path:
    """Create a guard.yaml with optional custom checks."""
    config: dict = {
        "version": 1,
        "project": {"name": "test", "language": "python"},
        "code": {
            "commit": {
                "format": True,
                "naming": True,
            },
            "push": {
                "lint": True,
            },
        },
    }
    if custom_checks:
        config["code"]["commit"]["checks"] = {
            "test": {"command": "pytest --cov", "timeout": 120},
        }
        config["code"]["push"]["checks"] = {
            "typecheck": {
                "command": "mypy src/",
                "timeout": 60,
                "types": ["python"],
            },
        }

    path = tmp_path / "guard.yaml"
    path.write_text(yaml.dump(config, default_flow_style=False), encoding="utf-8")
    return path


class TestValidationList:
    """Tests for guard validation list."""

    def test_lists_builtin_checks(self, tmp_path: Path) -> None:
        config = _write_config(tmp_path)
        result = runner.invoke(app, ["validation", "list", "--config", str(config)])
        assert result.exit_code == 0
        assert "format" in result.output
        assert "naming" in result.output
        assert "lint" in result.output

    def test_lists_custom_checks(self, tmp_path: Path) -> None:
        config = _write_config(tmp_path, custom_checks=True)
        result = runner.invoke(app, ["validation", "list", "--config", str(config)])
        assert result.exit_code == 0
        assert "test" in result.output
        assert "typecheck" in result.output

    def test_groups_by_stage(self, tmp_path: Path) -> None:
        config = _write_config(tmp_path, custom_checks=True)
        result = runner.invoke(app, ["validation", "list", "--config", str(config)])
        assert result.exit_code == 0
        output = result.output.lower()
        assert "commit" in output
        assert "push" in output

    def test_shows_builtin_tag(self, tmp_path: Path) -> None:
        config = _write_config(tmp_path)
        result = runner.invoke(app, ["validation", "list", "--config", str(config)])
        assert result.exit_code == 0
        assert "builtin" in result.output.lower()

    def test_shows_custom_tag(self, tmp_path: Path) -> None:
        config = _write_config(tmp_path, custom_checks=True)
        result = runner.invoke(app, ["validation", "list", "--config", str(config)])
        assert result.exit_code == 0
        assert "custom" in result.output.lower()


class TestValidationReport:
    """Tests for guard validation report."""

    def test_report_table_format(self, tmp_path: Path) -> None:
        config = _write_config(tmp_path, custom_checks=True)
        result = runner.invoke(app, ["validation", "report", "--config", str(config)])
        assert result.exit_code == 0
        assert "Name" in result.output
        assert "Stage" in result.output
        assert "Command" in result.output

    def test_report_includes_custom_details(self, tmp_path: Path) -> None:
        config = _write_config(tmp_path, custom_checks=True)
        result = runner.invoke(app, ["validation", "report", "--config", str(config)])
        assert result.exit_code == 0
        assert "pytest --cov" in result.output
        assert "mypy src/" in result.output
        assert "120" in result.output

    def test_report_includes_types(self, tmp_path: Path) -> None:
        config = _write_config(tmp_path, custom_checks=True)
        result = runner.invoke(app, ["validation", "report", "--config", str(config)])
        assert result.exit_code == 0
        assert "python" in result.output.lower()

    def test_report_builtin_only(self, tmp_path: Path) -> None:
        config = _write_config(tmp_path)
        result = runner.invoke(app, ["validation", "report", "--config", str(config)])
        assert result.exit_code == 0
        assert "format" in result.output
        assert "lint" in result.output
