"""Integration tests for Phase 3 Checker end-to-end (WP3.4).

Test matrix dimensions:
- CLI commands: check / verify / run / gate
- Check stages: commit / push (fail-fast)
- Check types: built-in pre-commit / custom command / build
- Report formats: terminal / gate / markdown
- Config variants: default / custom checks / disabled / build
- Full lifecycle scenarios
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from typer.testing import CliRunner

from ac_guard.checker.models import CheckReport, CheckResult
from ac_guard.cli.main import app
from ac_guard.reporter.formatting import format_markdown

runner = CliRunner()


def _write_config(tmp_path: Path, extra: dict | None = None) -> Path:
    """Write guard.yaml with optional extra config."""
    base = {"version": 1, "project": {"name": "test", "language": "python"}}
    if extra:
        base.update(extra)
    config = tmp_path / "guard.yaml"
    config.write_text(yaml.dump(base, default_flow_style=False))
    return config


def _config_with_checks(tmp_path: Path, *, fail: bool = False) -> Path:
    """Write config with custom checks (passing or failing)."""
    cmd = "exit 1" if fail else "echo ok"
    return _write_config(
        tmp_path,
        {
            "code": {
                "commit": {
                    "format": False,
                    "naming": False,
                    "checks": {"custom-commit": {"command": cmd}},
                },
                "push": {
                    "lint": False,
                    "checks": {"custom-push": {"command": "echo push-ok"}},
                },
            },
        },
    )


# ===========================================================================
# A. Full Lifecycle E2E
# ===========================================================================


class TestFullCheckLifecycle:
    """A1/A2: Complete check lifecycle scenarios."""

    def test_init_install_check_verify_gate_uninstall(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A1: Full lifecycle init→install→check→verify→gate→uninstall."""
        config = tmp_path / "guard.yaml"
        (tmp_path / ".git").mkdir()

        # Write config with no push checks (avoids real pytest subprocess)
        config.write_text(
            yaml.dump(
                {
                    "version": 1,
                    "project": {"name": "test", "language": "python"},
                    "code": {
                        "commit": {"format": False, "naming": False},
                        "push": {"lint": False},
                    },
                },
                default_flow_style=False,
            )
        )

        # install
        r = runner.invoke(app, ["install", "-a", "claude-code", "-c", str(config)])
        assert r.exit_code == 0

        # check (commit stage)
        with patch("ac_guard.checker.core.get_changed_files", return_value=[]):
            r = runner.invoke(app, ["check", "-c", str(config)])
        assert r.exit_code == 0
        assert "PASSED" in r.output

        # verify (push stage)
        with patch("ac_guard.checker.core.get_changed_files", return_value=[]):
            r = runner.invoke(app, ["verify", "-c", str(config)])
        assert r.exit_code == 0

        # gate run (commit)
        with patch("ac_guard.checker.core.get_changed_files", return_value=[]):
            r = runner.invoke(app, ["gate", "run", "-s", "commit", "-c", str(config)])
        assert r.exit_code == 0
        assert "passed" in r.output

        # uninstall
        monkeypatch.chdir(tmp_path)
        r = runner.invoke(app, ["uninstall", "--keep-config"])
        assert r.exit_code == 0

    def test_config_change_updates_check_behavior(self, tmp_path: Path) -> None:
        """A2: Modifying config changes check results after update."""
        # Start with passing custom check
        config = _config_with_checks(tmp_path, fail=False)
        (tmp_path / ".git").mkdir()
        runner.invoke(app, ["install", "-a", "claude-code", "-c", str(config)])

        with patch("ac_guard.checker.core.get_changed_files", return_value=[]):
            r = runner.invoke(app, ["check", "-c", str(config)])
        assert r.exit_code == 0

        # Change to failing check
        _config_with_checks(tmp_path, fail=True)
        runner.invoke(app, ["update", "-c", str(config)])

        with patch("ac_guard.checker.core.get_changed_files", return_value=[]):
            r = runner.invoke(app, ["check", "-c", str(config)])
        assert r.exit_code == 1
        assert "FAILED" in r.output


# ===========================================================================
# B. check Command
# ===========================================================================


class TestCheckCommand:
    """B1-B4: guard check command variants."""

    def test_default_config_passes(self, tmp_path: Path) -> None:
        """B1: Default config with no files → all checks pass."""
        config = _write_config(tmp_path)
        with patch("ac_guard.checker.core.get_changed_files", return_value=[]):
            r = runner.invoke(app, ["check", "-c", str(config)])
        assert r.exit_code == 0
        assert "PASSED" in r.output

    def test_custom_check_fails(self, tmp_path: Path) -> None:
        """B2: Failing custom check → exit 1 + FAILED."""
        config = _config_with_checks(tmp_path, fail=True)
        with patch("ac_guard.checker.core.get_changed_files", return_value=[]):
            r = runner.invoke(app, ["check", "-c", str(config)])
        assert r.exit_code == 1
        assert "FAILED" in r.output
        assert "custom-commit" in r.output

    def test_explicit_files(self, tmp_path: Path) -> None:
        """B3: --files passes explicit file list."""
        config = _write_config(tmp_path)
        with patch("ac_guard.checker.core.shutil.which", return_value=None):
            r = runner.invoke(app, ["check", "--files", "a.py", "-c", str(config)])
        assert r.exit_code == 0

    def test_missing_config(self, tmp_path: Path) -> None:
        """B4: Missing guard.yaml → exit 1."""
        r = runner.invoke(app, ["check", "-c", str(tmp_path / "guard.yaml")])
        assert r.exit_code == 1


# ===========================================================================
# C. verify Command
# ===========================================================================


class TestVerifyCommand:
    """C1-C4: guard verify command variants."""

    def test_push_all_pass(self, tmp_path: Path) -> None:
        """C1: Push stage all passing → exit 0."""
        config = _config_with_checks(tmp_path, fail=False)
        with patch("ac_guard.checker.core.get_changed_files", return_value=[]):
            r = runner.invoke(app, ["verify", "-c", str(config)])
        assert r.exit_code == 0

    def test_commit_fail_fast(self, tmp_path: Path) -> None:
        """C2: Commit failure → push not reached."""
        config = _config_with_checks(tmp_path, fail=True)
        with patch("ac_guard.checker.core.get_changed_files", return_value=[]):
            r = runner.invoke(app, ["verify", "-c", str(config)])
        assert r.exit_code == 1
        # Push-only check should NOT appear (fail-fast)
        assert "custom-push" not in r.output

    def test_skip_build(self, tmp_path: Path) -> None:
        """C3: --skip-build skips build step."""
        config = _write_config(tmp_path, {"build": {"command": "exit 1"}})
        with patch("ac_guard.checker.core.get_changed_files", return_value=[]):
            r = runner.invoke(app, ["verify", "--skip-build", "-c", str(config)])
        assert r.exit_code == 0

    def test_build_command_runs(self, tmp_path: Path) -> None:
        """C4: Build command runs in push stage."""
        config = _write_config(
            tmp_path,
            {
                "build": {"command": "echo built"},
                "code": {
                    "commit": {"format": False, "naming": False},
                    "push": {"lint": False},
                },
            },
        )
        with patch("ac_guard.checker.core.get_changed_files", return_value=[]):
            r = runner.invoke(app, ["verify", "-c", str(config)])
        assert r.exit_code == 0
        assert "build" in r.output.lower()


# ===========================================================================
# D. run Command
# ===========================================================================


class TestRunCommand:
    """D1-D4: guard run <name> command variants."""

    def test_builtin_format(self, tmp_path: Path) -> None:
        """D1: Running built-in format (skipped with no files)."""
        config = _write_config(tmp_path)
        with patch("ac_guard.checker.core.get_changed_files", return_value=[]):
            r = runner.invoke(app, ["run", "format", "-c", str(config)])
        assert r.exit_code == 0

    def test_custom_check_pass(self, tmp_path: Path) -> None:
        """D2: Running a passing custom check."""
        config = _config_with_checks(tmp_path, fail=False)
        with patch("ac_guard.checker.core.get_changed_files", return_value=[]):
            r = runner.invoke(app, ["run", "custom-commit", "-c", str(config)])
        assert r.exit_code == 0
        assert "custom-commit" in r.output

    def test_custom_check_fail(self, tmp_path: Path) -> None:
        """D3: Running a failing custom check."""
        config = _config_with_checks(tmp_path, fail=True)
        with patch("ac_guard.checker.core.get_changed_files", return_value=[]):
            r = runner.invoke(app, ["run", "custom-commit", "-c", str(config)])
        assert r.exit_code == 1

    def test_check_not_found(self, tmp_path: Path) -> None:
        """D4: Non-existent check → exit 1."""
        config = _write_config(tmp_path)
        r = runner.invoke(app, ["run", "nonexistent", "-c", str(config)])
        assert r.exit_code == 1
        assert "not found" in r.output


# ===========================================================================
# E. gate Command
# ===========================================================================


class TestGateCommand:
    """E1-E3: guard gate run command variants."""

    def test_commit_passed(self, tmp_path: Path) -> None:
        """E1: Commit stage pass → minimal 'passed' + exit 0."""
        config = _write_config(tmp_path)
        with patch("ac_guard.checker.core.get_changed_files", return_value=[]):
            r = runner.invoke(app, ["gate", "run", "-s", "commit", "-c", str(config)])
        assert r.exit_code == 0
        assert "passed" in r.output
        # Gate output should be minimal (no PASS/FAIL indicators)
        assert "[PASS]" not in r.output

    def test_commit_failed(self, tmp_path: Path) -> None:
        """E2: Commit stage fail → minimal 'failed' + exit 1."""
        config = _config_with_checks(tmp_path, fail=True)
        with patch("ac_guard.checker.core.get_changed_files", return_value=[]):
            r = runner.invoke(app, ["gate", "run", "-s", "commit", "-c", str(config)])
        assert r.exit_code == 1
        assert "failed" in r.output

    def test_push_passed(self, tmp_path: Path) -> None:
        """E3: Push stage pass → exit 0."""
        config = _config_with_checks(tmp_path, fail=False)
        with patch("ac_guard.checker.core.get_changed_files", return_value=[]):
            r = runner.invoke(app, ["gate", "run", "-s", "push", "-c", str(config)])
        assert r.exit_code == 0


# ===========================================================================
# F. Report Formats
# ===========================================================================


class TestReportFormats:
    """F1-F2: Report formatting integration."""

    def test_terminal_has_details(self, tmp_path: Path) -> None:
        """F1: Terminal output includes check details and counts."""
        config = _config_with_checks(tmp_path, fail=True)
        with patch("ac_guard.checker.core.get_changed_files", return_value=[]):
            r = runner.invoke(app, ["check", "-c", str(config)])
        assert "FAIL" in r.output
        assert "custom-commit" in r.output
        # Should have pass/fail count
        assert "/" in r.output  # e.g., "0/1"

    def test_markdown_rendering(self) -> None:
        """F2: Markdown report has table and emoji."""
        report = CheckReport(
            stage="commit",
            passed=False,
            results=[
                CheckResult(name="format", passed=True, duration_ms=10),
                CheckResult(name="test", passed=False, duration_ms=50),
            ],
            duration_ms=60,
        )
        md = format_markdown(report)
        assert "| format" in md or "format" in md
        assert "✅" in md
        assert "❌" in md
