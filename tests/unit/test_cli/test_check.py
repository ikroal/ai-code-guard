"""Tests for check, verify, run, and gate commands (WP3.3)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import yaml
from typer.testing import CliRunner

from ac_guard.cli.main import app

runner = CliRunner()


def _write_config(tmp_path: Path) -> Path:
    """Write a minimal guard.yaml and return path."""
    config = tmp_path / "guard.yaml"
    config.write_text(
        yaml.dump(
            {"version": 1, "project": {"name": "test", "language": "python"}},
            default_flow_style=False,
        ),
    )
    return config


def _write_config_with_checks(tmp_path: Path) -> Path:
    """Write guard.yaml with custom checks."""
    config = tmp_path / "guard.yaml"
    config.write_text(
        yaml.dump(
            {
                "version": 1,
                "project": {"name": "test", "language": "python"},
                "code": {
                    "commit": {
                        "format": False,
                        "naming": False,
                        "checks": {
                            "echo-test": {"command": "echo ok"},
                        },
                    },
                    "push": {
                        "lint": False,
                        "checks": {
                            "fail-test": {"command": "exit 1"},
                        },
                    },
                },
            },
            default_flow_style=False,
        ),
    )
    return config


# ---------------------------------------------------------------------------
# TestCheckCommand
# ---------------------------------------------------------------------------


class TestCheckCommand:
    """Tests for guard check command."""

    def test_check_passed(self, tmp_path: Path) -> None:
        """Passing checks return exit 0 and PASSED."""
        config = _write_config(tmp_path)
        with patch("ac_guard.checker.core.get_changed_files", return_value=[]):
            result = runner.invoke(app, ["check", "--config", str(config)])
        assert result.exit_code == 0
        assert "PASSED" in result.output

    def test_check_failed(self, tmp_path: Path) -> None:
        """Failing checks return exit 1 and FAILED."""
        config = _write_config_with_checks(tmp_path)
        # Add a failing check to commit stage
        config.write_text(
            yaml.dump(
                {
                    "version": 1,
                    "project": {"name": "test", "language": "python"},
                    "code": {
                        "commit": {
                            "format": False,
                            "naming": False,
                            "checks": {"fail": {"command": "exit 1"}},
                        },
                    },
                },
                default_flow_style=False,
            ),
        )
        with patch("ac_guard.checker.core.get_changed_files", return_value=[]):
            result = runner.invoke(app, ["check", "--config", str(config)])
        assert result.exit_code == 1
        assert "FAILED" in result.output

    def test_check_no_config(self, tmp_path: Path) -> None:
        """Missing guard.yaml exits with error."""
        config = tmp_path / "guard.yaml"
        result = runner.invoke(app, ["check", "--config", str(config)])
        assert result.exit_code == 1

    def test_check_with_files(self, tmp_path: Path) -> None:
        """--files option passes files to checker."""
        config = _write_config(tmp_path)
        # With format/naming enabled and explicit files, pre-commit will
        # be called but skip (no pre-commit config in tmp_path)
        with patch("ac_guard.checker.core.shutil.which", return_value=None):
            result = runner.invoke(
                app,
                [
                    "check",
                    "--files",
                    "a.py",
                    "--files",
                    "b.py",
                    "--config",
                    str(config),
                ],
            )
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# TestVerifyCommand
# ---------------------------------------------------------------------------


class TestVerifyCommand:
    """Tests for guard verify command."""

    def test_verify_passed(self, tmp_path: Path) -> None:
        """Passing verify returns exit 0."""
        config = _write_config(tmp_path)
        with patch("ac_guard.checker.core.get_changed_files", return_value=[]):
            result = runner.invoke(app, ["verify", "--config", str(config)])
        assert result.exit_code == 0
        assert "PASSED" in result.output

    def test_verify_skip_build(self, tmp_path: Path) -> None:
        """--skip-build skips build step."""
        config = _write_config(tmp_path)
        with patch("ac_guard.checker.core.get_changed_files", return_value=[]):
            result = runner.invoke(
                app, ["verify", "--skip-build", "--config", str(config)]
            )
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# TestRunCommand
# ---------------------------------------------------------------------------


class TestRunCommand:
    """Tests for guard run <name> command."""

    def test_run_builtin_format(self, tmp_path: Path) -> None:
        """Running built-in format check."""
        config = _write_config(tmp_path)
        with patch("ac_guard.checker.core.get_changed_files", return_value=[]):
            result = runner.invoke(app, ["run", "format", "--config", str(config)])
        # pre-commit skipped (no files) → passed
        assert result.exit_code == 0

    def test_run_custom_check(self, tmp_path: Path) -> None:
        """Running a custom check by name."""
        config = _write_config_with_checks(tmp_path)
        with patch("ac_guard.checker.core.get_changed_files", return_value=[]):
            result = runner.invoke(app, ["run", "echo-test", "--config", str(config)])
        assert result.exit_code == 0

    def test_run_not_found(self, tmp_path: Path) -> None:
        """Running non-existent check exits with error."""
        config = _write_config(tmp_path)
        result = runner.invoke(app, ["run", "nonexistent", "--config", str(config)])
        assert result.exit_code == 1
        assert "not found" in result.output


# ---------------------------------------------------------------------------
# TestGateRunCommand
# ---------------------------------------------------------------------------


class TestGateRunCommand:
    """Tests for guard gate run command."""

    def test_gate_commit_passed(self, tmp_path: Path) -> None:
        """Gate run with passing checks outputs minimal text."""
        config = _write_config(tmp_path)
        with patch("ac_guard.checker.core.get_changed_files", return_value=[]):
            result = runner.invoke(
                app, ["gate", "run", "--stage", "commit", "--config", str(config)]
            )
        assert result.exit_code == 0
        assert "passed" in result.output

    def test_gate_commit_failed(self, tmp_path: Path) -> None:
        """Gate run with failing checks exits 1."""
        config = tmp_path / "guard.yaml"
        config.write_text(
            yaml.dump(
                {
                    "version": 1,
                    "project": {"name": "test", "language": "python"},
                    "code": {
                        "commit": {
                            "format": False,
                            "naming": False,
                            "checks": {"fail": {"command": "exit 1"}},
                        },
                    },
                },
                default_flow_style=False,
            ),
        )
        with patch("ac_guard.checker.core.get_changed_files", return_value=[]):
            result = runner.invoke(
                app, ["gate", "run", "--stage", "commit", "--config", str(config)]
            )
        assert result.exit_code == 1
        assert "failed" in result.output

    def test_gate_push(self, tmp_path: Path) -> None:
        """Gate run push stage works."""
        config = _write_config(tmp_path)
        with patch("ac_guard.checker.core.get_changed_files", return_value=[]):
            result = runner.invoke(
                app, ["gate", "run", "--stage", "push", "--config", str(config)]
            )
        assert result.exit_code == 0
        assert "passed" in result.output


class TestJsonOutput:
    """Tests for --format json output."""

    def test_check_json_output(self, tmp_path: Path) -> None:
        """check --format json outputs valid JSON."""
        import json

        config = _write_config(tmp_path)
        with patch("ac_guard.checker.core.get_changed_files", return_value=[]):
            result = runner.invoke(
                app, ["check", "--config", str(config), "--format", "json"]
            )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["stage"] == "commit"
        assert data["passed"] is True
        assert "results" in data

    def test_verify_json_output(self, tmp_path: Path) -> None:
        """verify --format json outputs valid JSON."""
        import json

        config = _write_config(tmp_path)
        with patch("ac_guard.checker.core.get_changed_files", return_value=[]):
            result = runner.invoke(
                app,
                [
                    "verify",
                    "--skip-build",
                    "--config",
                    str(config),
                    "--format",
                    "json",
                ],
            )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["stage"] == "push"
        assert "results" in data
