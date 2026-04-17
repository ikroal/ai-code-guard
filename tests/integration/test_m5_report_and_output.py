"""Integration tests for M5 Report, JSON output, and Validation (WP5.5).

Three dimensions covering M5's output-side extensions:

    D1: PR Report — Checker → Markdown → Channel.send (mock HTTP)
    D2: JSON Output — CLI --format json → valid machine-readable JSON
    D3: Validation — guard.yaml → validation list/report reflects config
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml
from typer.testing import CliRunner

from ac_guard.checker.core import run_stage
from ac_guard.cli.main import app
from ac_guard.config.models import PrReportConfig
from ac_guard.reporter.channel_base import post_pr_comment
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
            "commit": {
                "format": True,
                "naming": True,
                "checks": {
                    "unit-test": {
                        "command": "pytest tests/unit",
                        "timeout": 120,
                    },
                },
            },
            "push": {
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
    """D1: Config → Checker → Markdown → Channel.send."""

    def test_check_report_to_markdown_to_channel(self, tmp_path: Path) -> None:
        """D1-1: Real CheckReport → format_markdown → post_pr_comment (mock HTTP)."""
        config = _init_and_install(tmp_path)
        resolved_config = _resolve(config)

        # Run real checker
        report = run_stage("commit", resolved_config.code, tmp_path)

        # Markdown should render without error
        markdown = format_markdown(report)
        assert "✅" in markdown or "❌" in markdown  # emoji indicators
        assert report.stage in markdown or "commit" in markdown.lower()

        # post_pr_comment should call channel.send with the markdown
        pr_config = PrReportConfig(enabled=True, platform="github")
        mock_resp = MagicMock()
        mock_resp.status = 201
        mock_resp.read.return_value = b'{"id":1}'
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with (
            patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen,
            patch.dict(
                "os.environ",
                {
                    "GITHUB_TOKEN": "ghp_test",
                    "GITHUB_REPOSITORY": "owner/repo",
                    "GITHUB_REF": "refs/pull/1/merge",
                },
            ),
        ):
            post_pr_comment(report, pr_config, locale="en")
            mock_urlopen.assert_called_once()
            req = mock_urlopen.call_args[0][0]
            body = json.loads(req.data)
            assert "body" in body
            assert len(body["body"]) > 0

    def test_send_failure_does_not_affect_check(self, tmp_path: Path) -> None:
        """D1-2: post_pr_comment failure → no exception, stderr warning."""
        config = _init_and_install(tmp_path)
        resolved_config = _resolve(config)
        report = run_stage("commit", resolved_config.code, tmp_path)

        pr_config = PrReportConfig(enabled=True, platform="github")

        # No env vars → channel will fail → should not raise
        with patch.dict("os.environ", {}, clear=False):
            import os

            os.environ.pop("GITHUB_TOKEN", None)
            os.environ.pop("GITHUB_REPOSITORY", None)
            post_pr_comment(report, pr_config, locale="en")
            # If we get here without exception, the test passes

    def test_disabled_pr_report_skips(self, tmp_path: Path) -> None:
        """D1-3: enabled=False → no HTTP call."""
        config = _init_and_install(tmp_path)
        resolved_config = _resolve(config)
        report = run_stage("commit", resolved_config.code, tmp_path)

        pr_config = PrReportConfig(enabled=False)
        with patch("urllib.request.urlopen") as mock_urlopen:
            post_pr_comment(report, pr_config, locale="en")
            mock_urlopen.assert_not_called()


# ---------------------------------------------------------------------------
# D2: JSON Machine-Readable Output
# ---------------------------------------------------------------------------


class TestJsonOutput:
    """D2: CLI --format json → valid JSON with correct fields."""

    def test_check_json_end_to_end(self, tmp_path: Path) -> None:
        """D2-1: guard check --format json via real CLI."""
        config = _init_and_install(tmp_path)

        result = runner.invoke(
            app, ["check", "--config", str(config), "--format", "json"]
        )
        assert result.exit_code == 0

        data = json.loads(result.output)
        assert data["stage"] == "commit"
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
                "commit": {
                    "format": False,
                    "naming": False,
                    "checks": {"fail": {"command": "exit 1"}},
                },
            },
        }
        config = tmp_path / "guard.yaml"
        config.write_text(
            yaml.dump(config_data, default_flow_style=False), encoding="utf-8"
        )

        result = runner.invoke(
            app, ["check", "--config", str(config), "--format", "json"]
        )
        assert result.exit_code == 1

        # Output must still be valid JSON even on failure
        data = json.loads(result.output)
        assert data["passed"] is False
        assert any(not r["passed"] for r in data["results"])


# ---------------------------------------------------------------------------
# D3: Validation Configuration Discovery
# ---------------------------------------------------------------------------


class TestValidationDiscovery:
    """D3: guard.yaml → validation list/report reflects config."""

    def test_list_with_custom_checks(self, tmp_path: Path) -> None:
        """D3-1: Custom checks appear grouped by stage."""
        config = _write_config_with_checks(tmp_path)

        result = runner.invoke(app, ["validation", "list", "--config", str(config)])
        assert result.exit_code == 0

        output = result.output
        # Builtin checks present
        assert "format" in output
        assert "naming" in output
        assert "lint" in output
        # Custom checks present
        assert "unit-test" in output
        assert "typecheck" in output
        # Stages present
        assert "Commit" in output or "commit" in output.lower()
        assert "Push" in output or "push" in output.lower()

    def test_report_with_custom_checks(self, tmp_path: Path) -> None:
        """D3-2: Report table includes command, timeout, types."""
        config = _write_config_with_checks(tmp_path)

        result = runner.invoke(app, ["validation", "report", "--config", str(config)])
        assert result.exit_code == 0

        output = result.output
        assert "pytest tests/unit" in output
        assert "mypy src/" in output
        assert "120" in output
        assert "python" in output.lower()

    def test_list_default_config(self, tmp_path: Path) -> None:
        """D3-3: Default init config shows builtin checks."""
        config = tmp_path / "guard.yaml"
        runner.invoke(app, ["init", "--language", "python", "--output", str(config)])

        result = runner.invoke(app, ["validation", "list", "--config", str(config)])
        assert result.exit_code == 0

        output = result.output
        assert "builtin" in output.lower()
        assert "format" in output
        assert "naming" in output
        assert "lint" in output


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _resolve(config_path: Path):
    """Load and resolve config."""
    from ac_guard.config.merger import resolve_config

    return resolve_config(config_path)
