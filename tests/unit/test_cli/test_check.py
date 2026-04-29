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


# ---------------------------------------------------------------------------
# TestCheckCommand
# ---------------------------------------------------------------------------


class TestCheckCommand:
    """Tests for guard check command."""

    def test_check_passed(self, tmp_path: Path) -> None:
        """Passing checks return exit 0 and PASSED."""
        config = _write_config(tmp_path)
        with patch("ac_guard.code_gate.core.get_changed_files", return_value=[]):
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
        with patch("ac_guard.code_gate.core.get_changed_files", return_value=[]):
            result = runner.invoke(app, ["check", "--config", str(config)])
        assert result.exit_code == 1
        assert "FAILED" in result.output

    def test_check_no_config(self, tmp_path: Path) -> None:
        """Missing guard.yaml exits with error."""
        config = tmp_path / "guard.yaml"
        result = runner.invoke(app, ["check", "--config", str(config)])
        assert result.exit_code == 1

    def test_check_with_files(self, tmp_path: Path) -> None:
        """--files option passes files to code_gate."""
        config = _write_config(tmp_path)
        # With format/naming enabled and explicit files, pre-commit will
        # be called but skip (no pre-commit config in tmp_path)
        with patch("ac_guard.code_gate.core.shutil.which", return_value=None):
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
        with patch("ac_guard.code_gate.core.get_changed_files", return_value=[]):
            result = runner.invoke(app, ["verify", "--config", str(config)])
        assert result.exit_code == 0
        assert "PASSED" in result.output

    def test_verify_skip_build(self, tmp_path: Path) -> None:
        """--skip-build skips build step."""
        config = _write_config(tmp_path)
        with patch("ac_guard.code_gate.core.get_changed_files", return_value=[]):
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
        with patch("ac_guard.code_gate.core.get_changed_files", return_value=[]):
            result = runner.invoke(app, ["run", "format", "--config", str(config)])
        # pre-commit skipped (no files) → passed
        assert result.exit_code == 0

    def test_run_custom_check(self, tmp_path: Path) -> None:
        """Running a custom check by name."""
        config = _write_config_with_checks(tmp_path)
        with patch("ac_guard.code_gate.core.get_changed_files", return_value=[]):
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
        with patch("ac_guard.code_gate.core.get_changed_files", return_value=[]):
            result = runner.invoke(
                app, ["gate", "run", "--stage", "pre-commit", "--config", str(config)]
            )
        assert result.exit_code == 0
        assert "PASSED" in result.output

    def test_gate_commit_failed(self, tmp_path: Path) -> None:
        """Gate run with failing checks exits 1."""
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
        with patch("ac_guard.code_gate.core.get_changed_files", return_value=[]):
            result = runner.invoke(
                app, ["gate", "run", "--stage", "pre-commit", "--config", str(config)]
            )
        assert result.exit_code == 1
        assert "FAILED" in result.output

    def test_gate_push(self, tmp_path: Path) -> None:
        """Gate run push stage works."""
        config = _write_config(tmp_path)
        with patch("ac_guard.code_gate.core.get_changed_files", return_value=[]):
            result = runner.invoke(
                app, ["gate", "run", "--stage", "pre-push", "--config", str(config)]
            )
        assert result.exit_code == 0
        assert "PASSED" in result.output


class TestRunPrecommitStage:
    """White-box tests for cli/check.py _run_precommit_stage helper.

    Covers the D3b passthrough path used by gate_run_command for stages
    not in BUCKET_AWARE_STAGES (commit-msg / pre-merge-commit /
    pre-rebase). The helper delegates to ``pre-commit run --hook-stage``
    and propagates its exit code.
    """

    def test_returns_subprocess_returncode(self, tmp_path: Path) -> None:
        """Exit code from the pre-commit subprocess propagates verbatim."""
        from subprocess import CompletedProcess

        from ac_guard.cli.check import _run_precommit_stage

        with patch("ac_guard.cli.check.subprocess.run") as mock_run:
            mock_run.return_value = CompletedProcess([], returncode=42)
            assert _run_precommit_stage("pre-rebase", tmp_path) == 42

    def test_invokes_pre_commit_with_hook_stage(self, tmp_path: Path) -> None:
        """Command starts with `pre-commit run --hook-stage <stage>`."""
        from subprocess import CompletedProcess

        from ac_guard.cli.check import _run_precommit_stage

        with patch("ac_guard.cli.check.subprocess.run") as mock_run:
            mock_run.return_value = CompletedProcess([], returncode=0)
            _run_precommit_stage("pre-merge-commit", tmp_path)
            cmd = mock_run.call_args.args[0]
            assert cmd[:4] == [
                "pre-commit",
                "run",
                "--hook-stage",
                "pre-merge-commit",
            ]

    def test_commit_msg_argv_forwarded(self, tmp_path: Path) -> None:
        """commit-msg with argv passes msg file via --commit-msg-filename."""
        from subprocess import CompletedProcess

        from ac_guard.cli.check import _run_precommit_stage

        with patch("ac_guard.cli.check.subprocess.run") as mock_run:
            mock_run.return_value = CompletedProcess([], returncode=0)
            _run_precommit_stage("commit-msg", tmp_path, argv=["/tmp/msg-file"])
            cmd = mock_run.call_args.args[0]
            assert "--commit-msg-filename" in cmd
            assert "/tmp/msg-file" in cmd
            assert "--all-files" not in cmd

    def test_commit_msg_no_argv_falls_back_to_all_files(self, tmp_path: Path) -> None:
        """commit-msg without argv falls back to --all-files."""
        from subprocess import CompletedProcess

        from ac_guard.cli.check import _run_precommit_stage

        with patch("ac_guard.cli.check.subprocess.run") as mock_run:
            mock_run.return_value = CompletedProcess([], returncode=0)
            _run_precommit_stage("commit-msg", tmp_path, argv=None)
            cmd = mock_run.call_args.args[0]
            assert "--all-files" in cmd
            assert "--commit-msg-filename" not in cmd

    def test_non_commit_msg_uses_all_files_even_with_argv(self, tmp_path: Path) -> None:
        """Non-commit-msg stages always use --all-files; argv is ignored."""
        from subprocess import CompletedProcess

        from ac_guard.cli.check import _run_precommit_stage

        with patch("ac_guard.cli.check.subprocess.run") as mock_run:
            mock_run.return_value = CompletedProcess([], returncode=0)
            _run_precommit_stage("pre-rebase", tmp_path, argv=["arg1"])
            cmd = mock_run.call_args.args[0]
            assert "--all-files" in cmd
            assert "--commit-msg-filename" not in cmd

    def test_passes_cwd_and_check_false(self, tmp_path: Path) -> None:
        """project_root is forwarded as cwd; check=False so we own exit code."""
        from subprocess import CompletedProcess

        from ac_guard.cli.check import _run_precommit_stage

        with patch("ac_guard.cli.check.subprocess.run") as mock_run:
            mock_run.return_value = CompletedProcess([], returncode=0)
            _run_precommit_stage("pre-merge-commit", tmp_path)
            assert mock_run.call_args.kwargs["cwd"] == tmp_path
            assert mock_run.call_args.kwargs["check"] is False


class TestJsonOutput:
    """Tests for --format json output."""

    def test_check_json_output(self, tmp_path: Path) -> None:
        """check --format json outputs valid JSON."""
        import json

        config = _write_config(tmp_path)
        with patch("ac_guard.code_gate.core.get_changed_files", return_value=[]):
            result = runner.invoke(
                app, ["check", "--config", str(config), "--format", "json"]
            )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["stage"] == "pre-commit"
        assert data["passed"] is True
        assert "results" in data

    def test_verify_json_output(self, tmp_path: Path) -> None:
        """verify --format json outputs valid JSON."""
        import json

        config = _write_config(tmp_path)
        with patch("ac_guard.code_gate.core.get_changed_files", return_value=[]):
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
        assert data["stage"] == "pre-push"
        assert "results" in data


# ---------------------------------------------------------------------------
# TestCliAutoPostPrComment — WP6.1 / Issue #66
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
    """check / verify / gate run auto-trigger post_pr_comment (WP6.1)."""

    def test_check_calls_post_pr_comment_with_resolved_config(
        self, tmp_path: Path
    ) -> None:
        """check dispatches post_pr_comment with report + pr_report + locale."""
        config = _write_config_with_pr_report(tmp_path, enabled=True)
        with (
            patch("ac_guard.code_gate.core.get_changed_files", return_value=[]),
            patch("ac_guard.cli.check._maybe_post_pr") as mock_post,
        ):
            result = runner.invoke(app, ["check", "--config", str(config)])
        assert result.exit_code == 0
        assert mock_post.call_count == 1
        pos_args, _kw_args = mock_post.call_args
        report_arg, pr_config_arg, locale_arg = pos_args
        assert report_arg.stage == "pre-commit"
        assert report_arg.passed is True
        assert pr_config_arg.enabled is True
        assert pr_config_arg.platform == "github"
        assert locale_arg == "zh-CN"

    def test_check_passes_disabled_config_through(self, tmp_path: Path) -> None:
        """Even when disabled, CLI calls post_pr_comment (primitive self-gates)."""
        config = _write_config_with_pr_report(tmp_path, enabled=False)
        with (
            patch("ac_guard.code_gate.core.get_changed_files", return_value=[]),
            patch("ac_guard.cli.check._maybe_post_pr") as mock_post,
        ):
            result = runner.invoke(app, ["check", "--config", str(config)])
        assert result.exit_code == 0
        assert mock_post.call_count == 1
        pos_args, _ = mock_post.call_args
        _report, pr_config_arg, _locale = pos_args
        assert pr_config_arg.enabled is False

    def test_verify_calls_post_pr_comment(self, tmp_path: Path) -> None:
        """verify also dispatches post_pr_comment at end."""
        config = _write_config_with_pr_report(tmp_path, enabled=True)
        with (
            patch("ac_guard.code_gate.core.get_changed_files", return_value=[]),
            patch("ac_guard.cli.check._maybe_post_pr") as mock_post,
        ):
            result = runner.invoke(
                app, ["verify", "--skip-build", "--config", str(config)]
            )
        assert result.exit_code == 0
        assert mock_post.call_count == 1
        pos_args, _ = mock_post.call_args
        report_arg, _, _ = pos_args
        assert report_arg.stage == "pre-push"

    def test_gate_run_calls_post_pr_comment(self, tmp_path: Path) -> None:
        """gate run also dispatches post_pr_comment at end."""
        config = _write_config_with_pr_report(tmp_path, enabled=True)
        with (
            patch("ac_guard.code_gate.core.get_changed_files", return_value=[]),
            patch("ac_guard.cli.check._maybe_post_pr") as mock_post,
        ):
            result = runner.invoke(
                app, ["gate", "run", "--stage", "pre-commit", "--config", str(config)]
            )
        assert result.exit_code == 0
        assert mock_post.call_count == 1
        pos_args, _ = mock_post.call_args
        report_arg, _, _ = pos_args
        assert report_arg.stage == "pre-commit"

    def test_run_does_not_call_post_pr_comment(self, tmp_path: Path) -> None:
        """run is intentionally out of scope (WP6.1): single-check runner.

        Fixates the decision: enabling per-check runs would create PR noise
        (one comment per check). Re-evaluate in a follow-up issue if needed.
        """
        config = _write_config_with_checks(tmp_path)
        with (
            patch("ac_guard.code_gate.core.get_changed_files", return_value=[]),
            patch("ac_guard.cli.check._maybe_post_pr") as mock_post,
        ):
            result = runner.invoke(app, ["run", "echo-test", "--config", str(config)])
        assert result.exit_code == 0
        assert mock_post.call_count == 0
