"""Tests for status, doctor, and agents commands (WP1.5c)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from ai_guard.cli.main import app
from ai_guard.generator.models import STATE_FILE, GeneratedState

runner = CliRunner()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _write_guard_yaml(tmp_path: Path, data: dict | None = None) -> Path:
    """Write a guard.yaml and return its path."""
    config = tmp_path / "guard.yaml"
    if data is None:
        data = {"version": 1, "project": {"name": "test", "language": "python"}}
    config.write_text(yaml.dump(data, default_flow_style=False), encoding="utf-8")
    return config


def _config_hash(path: Path) -> str:
    """Compute config hash matching merger._compute_config_hash."""
    return hashlib.sha256(path.read_bytes()).hexdigest()[:8]


def _write_state(
    project_root: Path,
    agents: list[str] | None = None,
    config_hash: str = "abcd1234",
    artifacts: list[str] | None = None,
) -> GeneratedState:
    """Write a state.json and return the GeneratedState."""
    state = GeneratedState(
        ai_guard_version="0.1.0",
        installed_agents=agents or ["claude-code"],
        config_hash=config_hash,
        artifacts=artifacts or ["CLAUDE.md", ".ai-guard/policy.json"],
    )
    state_path = project_root / STATE_FILE
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(state.to_json(), encoding="utf-8")
    return state


@pytest.fixture
def installed_project(tmp_path: Path) -> Path:
    """Project with guard.yaml, .git, state.json, and artifacts."""
    config = _write_guard_yaml(tmp_path)
    (tmp_path / ".git").mkdir()
    config_hash = _config_hash(config)
    _write_state(
        tmp_path,
        agents=["claude-code"],
        config_hash=config_hash,
        artifacts=["CLAUDE.md", ".ai-guard/policy.json", ".pre-commit-config.yaml"],
    )
    # Create actual artifact files
    (tmp_path / "CLAUDE.md").write_text("# Rules\n")
    (tmp_path / ".ai-guard" / "policy.json").write_text(
        json.dumps({"config_hash": config_hash})
    )
    (tmp_path / ".pre-commit-config.yaml").write_text("repos: []\n")
    return tmp_path


# ---------------------------------------------------------------------------
# TestStatusCommand
# ---------------------------------------------------------------------------


class TestStatusCommand:
    """Tests for guard status command."""

    def test_status_shows_installed_agents(self, installed_project: Path) -> None:
        """status shows which agents are installed."""
        config = installed_project / "guard.yaml"
        result = runner.invoke(app, ["status", "--config", str(config)])
        assert result.exit_code == 0
        assert "claude-code" in result.output

    def test_status_not_installed(self, tmp_path: Path) -> None:
        """status when not installed reports it."""
        _write_guard_yaml(tmp_path)
        config = tmp_path / "guard.yaml"
        result = runner.invoke(app, ["status", "--config", str(config)])
        assert result.exit_code == 0
        assert "not installed" in result.output.lower()

    def test_status_detects_drift(self, installed_project: Path) -> None:
        """status detects config drift when guard.yaml changed."""
        config = installed_project / "guard.yaml"
        # Modify config to create drift
        config.write_text(
            yaml.dump(
                {"version": 1, "project": {"name": "changed", "language": "go"}},
                default_flow_style=False,
            ),
        )
        result = runner.invoke(app, ["status", "--config", str(config)])
        assert result.exit_code == 0
        assert "drift" in result.output.lower() or "changed" in result.output.lower()

    def test_status_no_drift_when_synced(self, installed_project: Path) -> None:
        """status shows no drift when config hash matches."""
        config = installed_project / "guard.yaml"
        result = runner.invoke(app, ["status", "--config", str(config)])
        assert result.exit_code == 0
        assert (
            "up to date" in result.output.lower() or "synced" in result.output.lower()
        )

    def test_status_reports_missing_artifacts(self, installed_project: Path) -> None:
        """status reports artifacts listed in state but missing from disk."""
        config = installed_project / "guard.yaml"
        # Remove an artifact
        (installed_project / "CLAUDE.md").unlink()
        result = runner.invoke(app, ["status", "--config", str(config)])
        assert result.exit_code == 0
        assert "CLAUDE.md" in result.output

    def test_status_with_rules_flag(self, installed_project: Path) -> None:
        """status --rules shows rule listing."""
        config = installed_project / "guard.yaml"
        result = runner.invoke(app, ["status", "--rules", "--config", str(config)])
        assert result.exit_code == 0
        # Should show rules section (system protection rules at minimum)
        assert "rule" in result.output.lower()

    def test_status_version_mismatch(self, installed_project: Path) -> None:
        """status detects tool version mismatch."""
        config = installed_project / "guard.yaml"
        # Set state version to something different
        state_path = installed_project / STATE_FILE
        state = GeneratedState.from_json(state_path.read_text())
        state.ai_guard_version = "99.99.99"
        state_path.write_text(state.to_json())
        result = runner.invoke(app, ["status", "--config", str(config)])
        assert result.exit_code == 0
        assert "version" in result.output.lower()


# ---------------------------------------------------------------------------
# TestDoctorCommand
# ---------------------------------------------------------------------------


class TestDoctorCommand:
    """Tests for guard doctor command."""

    def test_doctor_checks_python(self, installed_project: Path) -> None:
        """doctor checks Python version."""
        config = installed_project / "guard.yaml"
        result = runner.invoke(app, ["doctor", "--config", str(config)])
        assert result.exit_code == 0
        assert "python" in result.output.lower()

    def test_doctor_checks_git(self, installed_project: Path) -> None:
        """doctor checks git availability."""
        config = installed_project / "guard.yaml"
        result = runner.invoke(app, ["doctor", "--config", str(config)])
        assert result.exit_code == 0
        assert "git" in result.output.lower()

    def test_doctor_checks_config(self, installed_project: Path) -> None:
        """doctor validates guard.yaml."""
        config = installed_project / "guard.yaml"
        result = runner.invoke(app, ["doctor", "--config", str(config)])
        assert result.exit_code == 0
        assert (
            "guard.yaml" in result.output.lower() or "config" in result.output.lower()
        )

    def test_doctor_not_initialized(self, tmp_path: Path) -> None:
        """doctor reports when not initialized."""
        config = tmp_path / "guard.yaml"
        result = runner.invoke(app, ["doctor", "--config", str(config)])
        assert result.exit_code == 0
        assert "guard.yaml" in result.output.lower()

    def test_doctor_checks_artifacts(self, installed_project: Path) -> None:
        """doctor checks artifact integrity."""
        config = installed_project / "guard.yaml"
        result = runner.invoke(app, ["doctor", "--config", str(config)])
        assert result.exit_code == 0
        # Should mention artifacts or files check
        assert "artifact" in result.output.lower() or "file" in result.output.lower()

    def test_doctor_checks_pre_commit(self, installed_project: Path) -> None:
        """doctor checks pre-commit availability."""
        config = installed_project / "guard.yaml"
        result = runner.invoke(app, ["doctor", "--config", str(config)])
        assert result.exit_code == 0
        assert "pre-commit" in result.output.lower()


# ---------------------------------------------------------------------------
# TestAgentsCommand
# ---------------------------------------------------------------------------


class TestAgentsCommand:
    """Tests for guard agents command."""

    def test_agents_lists_all(self) -> None:
        """agents shows all supported agents."""
        result = runner.invoke(app, ["agents"])
        assert result.exit_code == 0
        assert "claude-code" in result.output.lower()
        assert "cursor" in result.output.lower()
        assert "opencode" in result.output.lower()
        assert "copilot" in result.output.lower()
        assert "kilocode" in result.output.lower()

    def test_agents_shows_capabilities(self) -> None:
        """agents shows capability information."""
        result = runner.invoke(app, ["agents"])
        assert result.exit_code == 0
        assert "block" in result.output.lower()

    def test_agents_shows_installed_status(
        self, installed_project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """agents marks installed agents."""
        monkeypatch.chdir(installed_project)
        result = runner.invoke(app, ["agents"])
        assert result.exit_code == 0
        # claude-code should be marked as installed
        output_lower = result.output.lower()
        assert "claude-code" in output_lower
        assert "installed" in output_lower

    def test_agents_no_installation(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """agents works when nothing is installed."""
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["agents"])
        assert result.exit_code == 0
        # Should still list all agents
        assert "claude-code" in result.output.lower()

    def test_agents_shows_rule_doc_path(self) -> None:
        """agents shows rule document paths."""
        result = runner.invoke(app, ["agents"])
        assert result.exit_code == 0
        assert "claude.md" in result.output.lower()


class TestStatusJsonOutput:
    """Tests for status --format json."""

    def test_status_json_installed(self, installed_project: Path) -> None:
        """JSON output includes installation details."""
        config = installed_project / "guard.yaml"
        result = runner.invoke(
            app, ["status", "--config", str(config), "--format", "json"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["installed"] is True
        assert "claude-code" in data["installed_agents"]
        assert "config_hash" in data
        assert "artifacts" in data

    def test_status_json_not_installed(self, tmp_path: Path) -> None:
        """JSON output when not installed."""
        config = tmp_path / "guard.yaml"
        config.write_text("version: 1\n")
        result = runner.invoke(
            app, ["status", "--config", str(config), "--format", "json"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["installed"] is False
