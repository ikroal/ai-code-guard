"""Integration tests for M5 Report, JSON output, and Validation (WP5.5).

Three dimensions covering M5's output-side extensions:

    D1: PR Report — code_gate → Markdown → Channel.send (mock HTTP)
    D2: JSON Output — CLI --format json → valid machine-readable JSON
    D3: Validation — guard.yaml → validation list/report reflects config
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml
from typer.testing import CliRunner

from ac_guard.cli.main import app
from ac_guard.code_gate import gate_stage
from ac_guard.reporter import (
    ChannelError,
    GitPlatformCfg,
    NoPrContextError,
    ReportConfig,
)
from ac_guard.reporter import (
    report as reporter_report,
)
from ac_guard.reporter.core import FormatKind
from ac_guard.reporter.formatting import format_markdown

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _init_and_install(tmp_path: Path) -> Path:
    """Init config + install in tmp_path. Returns config path."""
    config = tmp_path / "guard.yaml"
    (tmp_path / ".git").mkdir()
    runner.invoke(app, ["init", "--language", "python", "--output", str(config)])
    runner.invoke(app, ["install", "--agent", "claude-code", "--config", str(config)])
    return config


def _write_config_with_checks(tmp_path: Path) -> Path:
    """Create guard.yaml with custom checks for validation tests."""
    config_data = {
        "version": 1,
        "project": {"name": "test-project", "language": "python"},
        "code": {
            "pre-commit": {
                "format": True,
                "checks": {
                    "unit-test": {
                        "command": "pytest tests/unit",
                        "timeout": 120,
                    },
                },
            },
            "pre-push": {
                "lint": True,
                "checks": {
                    "typecheck": {
                        "command": "mypy src/",
                        "timeout": 60,
                        "types": ["python"],
                    },
                },
            },
        },
    }
    config = tmp_path / "guard.yaml"
    config.write_text(
        yaml.dump(config_data, default_flow_style=False), encoding="utf-8"
    )
    return config


# ---------------------------------------------------------------------------
# D1: PR Report Publishing Flow
# ---------------------------------------------------------------------------


class TestPrReportFlow:
    """D1: code_gate outcome → report() with GitPlatformCfg → HTTP POST."""

    def test_report_outcome_to_git_platform(self, tmp_path: Path) -> None:
        """D1-1: Real StageOutcome → report() via GitPlatformCfg (mock HTTP)."""
        config = _init_and_install(tmp_path)
        resolved_config = _resolve(config)

        # Run real code_gate
        outcome = gate_stage("pre-commit", resolved_config.code, tmp_path)

        # Markdown should render without error (sanity check the formatter)
        markdown = format_markdown(outcome)
        assert "✅" in markdown or "❌" in markdown  # emoji indicators
        assert outcome.stage in markdown or "pre-commit" in markdown.lower()

        # report() with GitPlatformCfg + MARKDOWN should POST to github
        mock_resp = MagicMock()
        mock_resp.status = 201
        mock_resp.read.return_value = b'{"id":1}'
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        # GET list (empty) + POST create
        list_resp = MagicMock()
        list_resp.status = 200
        list_resp.read.return_value = b"[]"
        list_resp.__enter__ = MagicMock(return_value=list_resp)
        list_resp.__exit__ = MagicMock(return_value=False)

        call_count = 0

        def urlopen_side_effect(req: MagicMock) -> MagicMock:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return list_resp
            return mock_resp

        with (
            patch(
                "urllib.request.urlopen", side_effect=urlopen_side_effect
            ) as mock_urlopen,
            patch.dict(
                "os.environ",
                {
                    "GITHUB_TOKEN": "ghp_test",
                    "GITHUB_REPOSITORY": "owner/repo",
                    "GITHUB_REF": "refs/pull/1/merge",
                },
            ),
        ):
            reporter_report(
                outcome,
                ReportConfig(
                    channel=GitPlatformCfg(platform="github"),
                    format=FormatKind.MARKDOWN,
                    locale="en",
                ),
            )
            assert mock_urlopen.call_count == 2
            req = mock_urlopen.call_args_list[-1][0][0]
            body = json.loads(req.data)
            assert "body" in body
            assert len(body["body"]) > 0

    def test_non_blocking_swallows_failure(self, tmp_path: Path) -> None:
        """D1-2: report(non_blocking=True) → delivery failure does not raise."""
        config = _init_and_install(tmp_path)
        resolved_config = _resolve(config)
        outcome = gate_stage("pre-commit", resolved_config.code, tmp_path)

        # No env vars → channel will fail. non_blocking=True must absorb it.
        with patch.dict("os.environ", {}, clear=False):
            import os

            os.environ.pop("GITHUB_TOKEN", None)
            os.environ.pop("GITHUB_REPOSITORY", None)
            reporter_report(
                outcome,
                ReportConfig(
                    channel=GitPlatformCfg(platform="github"),
                    format=FormatKind.MARKDOWN,
                    locale="en",
                ),
                non_blocking=True,
            )
            # If we get here without exception, the test passes


# ---------------------------------------------------------------------------
# D2: JSON Machine-Readable Output
# ---------------------------------------------------------------------------


class TestJsonOutput:
    """D2: CLI --format json → valid JSON with correct fields."""

    def test_check_json_end_to_end(self, tmp_path: Path) -> None:
        """D2-1: guard check --format json via real CLI."""
        config = _init_and_install(tmp_path)

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
        assert isinstance(data["passed"], bool)
        assert isinstance(data["results"], list)
        assert "duration_ms" in data

    def test_status_json_end_to_end(self, tmp_path: Path) -> None:
        """D2-2: guard status --format json via real CLI."""
        config = _init_and_install(tmp_path)

        result = runner.invoke(
            app, ["status", "--config", str(config), "--format", "json"]
        )
        assert result.exit_code == 0

        data = json.loads(result.output)
        assert data["installed"] is True
        assert "claude-code" in data["installed_agents"]
        assert "config_hash" in data
        assert isinstance(data["artifacts"], list)
        assert len(data["artifacts"]) > 0

    def test_check_json_on_failure(self, tmp_path: Path) -> None:
        """D2-3: Failing check still outputs valid JSON, not mixed text."""
        (tmp_path / ".git").mkdir()
        config_data = {
            "version": 1,
            "project": {"name": "test", "language": "python"},
            "code": {
                "pre-commit": {
                    "format": False,
                    "checks": {"fail": {"command": "exit 1"}},
                },
            },
        }
        config = tmp_path / "guard.yaml"
        config.write_text(
            yaml.dump(config_data, default_flow_style=False), encoding="utf-8"
        )

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
        assert result.exit_code == 1

        # Output must still be valid JSON even on failure
        data = json.loads(result.output)
        assert data["passed"] is False
        assert any(not r["passed"] for r in data["results"])


# ---------------------------------------------------------------------------
# D3: Configuration Discovery (via `ac-guard show --section=code`)
# ---------------------------------------------------------------------------


class TestConfiguredCodeGatesDiscovery:
    """D3: ``show --section=code`` reflects the gates declared in guard.yaml.

    Replaces the retired ``validation list/report`` commands.
    """

    def test_text_lists_custom_checks_per_stage(self, tmp_path: Path) -> None:
        """D3-1: Custom checks appear grouped by stage in text format."""
        config = _write_config_with_checks(tmp_path)

        result = runner.invoke(
            app, ["show", "--section", "code", "--config", str(config)]
        )
        assert result.exit_code == 0

        output = result.output
        # Builtin checks present (D8: naming dropped).
        assert "format" in output
        assert "lint" in output
        # Custom checks present
        assert "unit-test" in output
        assert "typecheck" in output
        # Stages present
        assert "Commit" in output or "commit" in output.lower()
        assert "Push" in output or "push" in output.lower()

    def test_table_renders_command_timeout_types(self, tmp_path: Path) -> None:
        """D3-2: Table format includes command, timeout, types."""
        config = _write_config_with_checks(tmp_path)

        result = runner.invoke(
            app,
            ["show", "--section", "code", "--format", "table", "--config", str(config)],
        )
        assert result.exit_code == 0

        output = result.output
        assert "pytest tests/unit" in output
        assert "mypy src/" in output
        assert "120" in output
        assert "python" in output.lower()

    def test_default_init_config_shows_builtin_checks(self, tmp_path: Path) -> None:
        """D3-3: Default init config shows builtin checks under code section."""
        config = tmp_path / "guard.yaml"
        runner.invoke(app, ["init", "--language", "python", "--output", str(config)])

        result = runner.invoke(
            app, ["show", "--section", "code", "--config", str(config)]
        )
        assert result.exit_code == 0

        output = result.output
        assert "builtin" in output.lower()
        assert "format" in output
        assert "lint" in output


# ---------------------------------------------------------------------------
# D4: CLI Auto-Dispatch of PR Report (WP6.1 / Issue #66)
# ---------------------------------------------------------------------------


def _write_config_pr_report(
    tmp_path: Path, *, enabled: bool, platform: str = "github"
) -> Path:
    """Write a guard.yaml that enables PR reporting for the given platform."""
    (tmp_path / ".git").mkdir(exist_ok=True)
    config = tmp_path / "guard.yaml"
    config.write_text(
        yaml.dump(
            {
                "version": 1,
                "project": {"name": "test", "language": "python"},
                "output": {
                    "pr_report": {
                        "enabled": enabled,
                        "platform": platform,
                        "token_env": "GITHUB_TOKEN",
                    },
                },
            },
            default_flow_style=False,
        ),
        encoding="utf-8",
    )
    return config


class TestCliPrReportIntegration:
    """D4: CLI commands auto-dispatch post_pr_comment end-to-end (WP6.1)."""

    def test_cli_check_triggers_pr_comment_when_pr_exists(self, tmp_path: Path) -> None:
        """D4-1: guard check with pr_report.enabled=true → Channel.send called."""
        config = _write_config_pr_report(tmp_path, enabled=True)
        with (
            patch("ac_guard.code_gate.core._get_changed_files", return_value=[]),
            patch(
                "ac_guard.reporter.channels.github.GitHubChannel.output"
            ) as mock_send,
        ):
            result = runner.invoke(
                app, ["run", "--stage", "pre-commit", "--config", str(config)]
            )
        assert result.exit_code == 0
        assert mock_send.call_count == 1
        markdown_arg = mock_send.call_args[0][0]
        assert isinstance(markdown_arg, str)
        assert len(markdown_arg) > 0

    def test_cli_gate_run_triggers_pr_comment_when_pr_exists(
        self, tmp_path: Path
    ) -> None:
        """D4-2: guard gate run with pr_report.enabled=true → Channel.send called."""
        config = _write_config_pr_report(tmp_path, enabled=True)
        with (
            patch("ac_guard.code_gate.core._get_changed_files", return_value=[]),
            patch(
                "ac_guard.reporter.channels.github.GitHubChannel.output"
            ) as mock_send,
        ):
            result = runner.invoke(
                app, ["run", "--stage", "pre-commit", "--config", str(config)]
            )
        assert result.exit_code == 0
        assert mock_send.call_count == 1

    def test_cli_check_silent_when_no_pr_context(self, tmp_path: Path) -> None:
        """D4-3: NoPrContextError from channel.send → no stderr warning."""
        config = _write_config_pr_report(tmp_path, enabled=True)
        with (
            patch("ac_guard.code_gate.core._get_changed_files", return_value=[]),
            patch(
                "ac_guard.reporter.channels.github.GitHubChannel.output",
                side_effect=NoPrContextError("Cannot determine PR number"),
            ),
        ):
            result = runner.invoke(
                app,
                ["run", "--stage", "pre-commit", "--config", str(config)],
                catch_exceptions=False,
            )
        assert result.exit_code == 0
        combined = result.output + (
            result.stderr_bytes.decode("utf-8", errors="replace")
            if result.stderr_bytes
            else ""
        )
        assert "Warning: PR comment failed to post" not in combined
        assert "Cannot determine PR number" not in combined

    def test_cli_check_warns_when_channel_error(self, tmp_path: Path) -> None:
        """D4-4: Non-NoPrContext ChannelError → stderr warning preserved."""
        config = _write_config_pr_report(tmp_path, enabled=True)
        with (
            patch("ac_guard.code_gate.core._get_changed_files", return_value=[]),
            patch(
                "ac_guard.reporter.channels.github.GitHubChannel.output",
                side_effect=ChannelError("GitHub API returned 500"),
            ),
        ):
            # CliRunner merges stdout+stderr by default; check full output
            result = runner.invoke(
                app,
                ["run", "--stage", "pre-commit", "--config", str(config)],
                catch_exceptions=False,
            )
        assert result.exit_code == 0
        combined = result.output + (
            result.stderr_bytes.decode("utf-8", errors="replace")
            if result.stderr_bytes
            else ""
        )
        assert "Warning: report delivery failed" in combined
        assert "500" in combined

    def test_cli_check_disabled_skips_channel_entirely(self, tmp_path: Path) -> None:
        """D4-5: pr_report.enabled=false → channel.send never invoked."""
        config = _write_config_pr_report(tmp_path, enabled=False)
        with (
            patch("ac_guard.code_gate.core._get_changed_files", return_value=[]),
            patch(
                "ac_guard.reporter.channels.github.GitHubChannel.output"
            ) as mock_send,
        ):
            result = runner.invoke(
                app, ["run", "--stage", "pre-commit", "--config", str(config)]
            )
        assert result.exit_code == 0
        assert mock_send.call_count == 0


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _resolve(config_path: Path):
    """Load and resolve config."""
    from ac_guard.config.merger import resolve_config

    return resolve_config(config_path)
