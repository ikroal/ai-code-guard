"""Tests for the unified ``ac-guard run`` command.

Two operating modes share one command surface:

- Single-check (positional ``<name>``) → ``gate_check``; no PR comment.
- Full-stage (``--stage X`` only) → ``gate_stage``; posts PR comment
  when configured.
"""

from __future__ import annotations

import json
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
        encoding="utf-8",
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
                    "pre-commit": {
                        "format": False,
                        "checks": {
                            "echo-test": {"command": "echo ok"},
                        },
                    },
                    "pre-push": {
                        "lint": False,
                        "checks": {
                            "fail-test": {"command": "exit 1"},
                        },
                    },
                },
            },
            default_flow_style=False,
        ),
        encoding="utf-8",
    )
    return config


def _write_failing_commit_config(tmp_path: Path) -> Path:
    """Write guard.yaml with a single failing custom check on pre-commit."""
    config = tmp_path / "guard.yaml"
    config.write_text(
        yaml.dump(
            {
                "version": 1,
                "project": {"name": "test", "language": "python"},
                "code": {
                    "pre-commit": {
                        "format": False,
                        "checks": {"fail": {"command": "exit 1"}},
                    },
                },
            },
            default_flow_style=False,
        ),
        encoding="utf-8",
    )
    return config


# ---------------------------------------------------------------------------
# TestRunFullStage — full-stage mode (no <name>, --stage required)
# ---------------------------------------------------------------------------


class TestRunFullStage:
    """``ac-guard run --stage X`` (full-stage mode)."""

    def test_pre_commit_passed(self, tmp_path: Path) -> None:
        config = _write_config(tmp_path)
        with patch("ac_guard.code_gate.core._get_changed_files", return_value=[]):
            result = runner.invoke(
                app, ["run", "--stage", "pre-commit", "--config", str(config)]
            )
        assert result.exit_code == 0
        assert "PASSED" in result.output

    def test_pre_commit_failed(self, tmp_path: Path) -> None:
        config = _write_failing_commit_config(tmp_path)
        with patch("ac_guard.code_gate.core._get_changed_files", return_value=[]):
            result = runner.invoke(
                app, ["run", "--stage", "pre-commit", "--config", str(config)]
            )
        assert result.exit_code == 1
        assert "FAILED" in result.output

    def test_pre_push_passed(self, tmp_path: Path) -> None:
        config = _write_config(tmp_path)
        with patch("ac_guard.code_gate.core._get_changed_files", return_value=[]):
            result = runner.invoke(
                app, ["run", "--stage", "pre-push", "--config", str(config)]
            )
        assert result.exit_code == 0
        assert "PASSED" in result.output

    def test_pre_push_skip_build(self, tmp_path: Path) -> None:
        """--skip-build suppresses the build step on pre-push."""
        config = _write_config(tmp_path)
        with patch("ac_guard.code_gate.core._get_changed_files", return_value=[]):
            result = runner.invoke(
                app,
                [
                    "run",
                    "--stage",
                    "pre-push",
                    "--skip-build",
                    "--config",
                    str(config),
                ],
            )
        assert result.exit_code == 0

    def test_unknown_stage_exits_2(self, tmp_path: Path) -> None:
        """gate_stage raises ValueError for unknown stages → exit 2."""
        config = _write_config(tmp_path)
        result = runner.invoke(
            app, ["run", "--stage", "post-commit", "--config", str(config)]
        )
        assert result.exit_code == 2
        assert "Unknown stage" in result.output

    def test_no_config_exits_1(self, tmp_path: Path) -> None:
        """Missing guard.yaml exits with error."""
        config = tmp_path / "guard.yaml"
        result = runner.invoke(
            app, ["run", "--stage", "pre-commit", "--config", str(config)]
        )
        assert result.exit_code == 1


# ---------------------------------------------------------------------------
# TestRunSingleCheck — single-check mode (positional <name>)
# ---------------------------------------------------------------------------


class TestRunSingleCheck:
    """``ac-guard run <name>`` (single-check mode)."""

    def test_run_builtin_format(self, tmp_path: Path) -> None:
        config = _write_config(tmp_path)
        with patch("ac_guard.code_gate.core._get_changed_files", return_value=[]):
            result = runner.invoke(app, ["run", "format", "--config", str(config)])
        assert result.exit_code == 0

    def test_run_custom_check(self, tmp_path: Path) -> None:
        config = _write_config_with_checks(tmp_path)
        with patch("ac_guard.code_gate.core._get_changed_files", return_value=[]):
            result = runner.invoke(app, ["run", "echo-test", "--config", str(config)])
        assert result.exit_code == 0

    def test_run_not_found_exits_1(self, tmp_path: Path) -> None:
        """gate_check raises KeyError → exit 1 with available names."""
        config = _write_config_with_checks(tmp_path)
        result = runner.invoke(app, ["run", "nonexistent", "--config", str(config)])
        assert result.exit_code == 1
        assert "not found" in result.output

    def test_run_with_explicit_files(self, tmp_path: Path) -> None:
        """--files overrides auto-detection."""
        config = _write_config(tmp_path)
        with patch("ac_guard.code_gate.core.shutil.which", return_value=None):
            result = runner.invoke(
                app,
                [
                    "run",
                    "format",
                    "--files",
                    "a.py",
                    "--files",
                    "b.py",
                    "--config",
                    str(config),
                ],
            )
        assert result.exit_code == 0

    def test_run_stage_hint_routes_file_diff(self, tmp_path: Path) -> None:
        """--stage hint changes the diff range used for file collection."""
        config = _write_config_with_checks(tmp_path)
        with patch(
            "ac_guard.code_gate.core._get_changed_files", return_value=[]
        ) as mock_get:
            runner.invoke(
                app,
                [
                    "run",
                    "echo-test",
                    "--stage",
                    "pre-push",
                    "--config",
                    str(config),
                ],
            )
        assert mock_get.call_args.args[0] == "pre-push"


# ---------------------------------------------------------------------------
# TestRunArgvPassthrough — commit-msg argv via `--`
# ---------------------------------------------------------------------------


class TestRunArgvPassthrough:
    """commit-msg hook forwards ``$1`` via ``--message-file``."""

    def test_commit_msg_forwards_argv_to_delegation(self, tmp_path: Path) -> None:
        """``run --stage commit-msg --message-file X`` reaches _delegate_managed_stage."""
        config = _write_config(tmp_path)
        with patch(
            "ac_guard.code_gate.core._delegate_managed_stage", return_value=0
        ) as mock_delegate:
            result = runner.invoke(
                app,
                [
                    "run",
                    "--stage",
                    "commit-msg",
                    "--config",
                    str(config),
                    "--message-file",
                    "/tmp/COMMIT_EDITMSG",
                ],
            )
        assert result.exit_code == 0
        assert mock_delegate.call_args.kwargs["argv"] == ["/tmp/COMMIT_EDITMSG"]


# ---------------------------------------------------------------------------
# TestRunJsonOutput — --format json (full-stage mode)
# ---------------------------------------------------------------------------


class TestRunJsonOutput:
    """``--format json`` produces machine-readable output for full-stage runs."""

    def test_pre_commit_json(self, tmp_path: Path) -> None:
        config = _write_config(tmp_path)
        with patch("ac_guard.code_gate.core._get_changed_files", return_value=[]):
            result = runner.invoke(
                app,
                [
                    "run",
                    "--stage",
                    "pre-commit",
                    "--config",
                    str(config),
                    "--format",
                    "json",
                ],
            )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["stage"] == "pre-commit"
        assert data["passed"] is True

    def test_pre_push_json(self, tmp_path: Path) -> None:
        config = _write_config(tmp_path)
        with patch("ac_guard.code_gate.core._get_changed_files", return_value=[]):
            result = runner.invoke(
                app,
                [
                    "run",
                    "--stage",
                    "pre-push",
                    "--skip-build",
                    "--config",
                    str(config),
                    "--format",
                    "json",
                ],
            )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["stage"] == "pre-push"


# ---------------------------------------------------------------------------
# TestCliAutoPostPrComment — PR auto-post fires for full-stage only
# ---------------------------------------------------------------------------


def _write_config_with_pr_report(tmp_path: Path, *, enabled: bool) -> Path:
    """Write guard.yaml with output.pr_report.enabled set explicitly."""
    config = tmp_path / "guard.yaml"
    config.write_text(
        yaml.dump(
            {
                "version": 1,
                "project": {"name": "test", "language": "python"},
                "output": {
                    "locale": "zh-CN",
                    "pr_report": {
                        "enabled": enabled,
                        "platform": "github",
                        "token_env": "GITHUB_TOKEN",
                    },
                },
            },
            default_flow_style=False,
        ),
        encoding="utf-8",
    )
    return config


class TestCliAutoPostPrComment:
    """PR comment posting: full-stage runs fire it, single-check does not."""

    def test_full_stage_pre_commit_calls_post_pr(self, tmp_path: Path) -> None:
        config = _write_config_with_pr_report(tmp_path, enabled=True)
        with (
            patch("ac_guard.code_gate.core._get_changed_files", return_value=[]),
            patch("ac_guard.cli.check._maybe_post_pr") as mock_post,
        ):
            result = runner.invoke(
                app, ["run", "--stage", "pre-commit", "--config", str(config)]
            )
        assert result.exit_code == 0
        assert mock_post.call_count == 1
        report_arg, pr_config_arg, locale_arg = mock_post.call_args.args
        assert report_arg.stage == "pre-commit"
        assert pr_config_arg.enabled is True
        assert locale_arg == "zh-CN"

    def test_full_stage_disabled_pr_still_invokes(self, tmp_path: Path) -> None:
        """``_maybe_post_pr`` self-gates on pr_report.enabled (primitive call)."""
        config = _write_config_with_pr_report(tmp_path, enabled=False)
        with (
            patch("ac_guard.code_gate.core._get_changed_files", return_value=[]),
            patch("ac_guard.cli.check._maybe_post_pr") as mock_post,
        ):
            result = runner.invoke(
                app, ["run", "--stage", "pre-commit", "--config", str(config)]
            )
        assert result.exit_code == 0
        assert mock_post.call_count == 1
        _report, pr_config_arg, _locale = mock_post.call_args.args
        assert pr_config_arg.enabled is False

    def test_full_stage_pre_push_calls_post_pr(self, tmp_path: Path) -> None:
        config = _write_config_with_pr_report(tmp_path, enabled=True)
        with (
            patch("ac_guard.code_gate.core._get_changed_files", return_value=[]),
            patch("ac_guard.cli.check._maybe_post_pr") as mock_post,
        ):
            result = runner.invoke(
                app,
                [
                    "run",
                    "--stage",
                    "pre-push",
                    "--skip-build",
                    "--config",
                    str(config),
                ],
            )
        assert result.exit_code == 0
        assert mock_post.call_count == 1
        report_arg, _, _ = mock_post.call_args.args
        assert report_arg.stage == "pre-push"

    def test_single_check_does_not_call_post_pr(self, tmp_path: Path) -> None:
        """Single-check mode is a developer iteration tool — no PR noise."""
        config = _write_config_with_checks(tmp_path)
        with (
            patch("ac_guard.code_gate.core._get_changed_files", return_value=[]),
            patch("ac_guard.cli.check._maybe_post_pr") as mock_post,
        ):
            result = runner.invoke(app, ["run", "echo-test", "--config", str(config)])
        assert result.exit_code == 0
        assert mock_post.call_count == 0
