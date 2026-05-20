"""Tests for install, update, and uninstall commands (WP1.5b)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from ac_guard.cli.main import app
from ac_guard.generator import Installation, installation_path

runner = CliRunner()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def project_with_config(tmp_path: Path) -> Path:
    """Create a minimal project directory with guard.yaml and .git."""
    config = tmp_path / "guard.yaml"
    config.write_text(
        yaml.dump(
            {"version": 1, "project": {"name": "test", "language": "python"}},
            default_flow_style=False,
        ),
        encoding="utf-8",
    )
    (tmp_path / ".git").mkdir()
    return tmp_path


@pytest.fixture
def installed_project(project_with_config: Path) -> Path:
    """Create a project with an existing installation state."""
    state = Installation(
        ac_guard_version="0.1.0",
        installed_agents=["claude-code"],
        config_hash="abcd1234",
        artifacts=["CLAUDE.md", ".ac-guard/runtime.json"],
    )
    state_path = installation_path(project_with_config)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(state.to_json(), encoding="utf-8")
    # Create the artifact files so uninstall can delete them
    (project_with_config / "CLAUDE.md").write_text("# Rules\n", encoding="utf-8")
    policy_dir = project_with_config / ".ac-guard"
    (policy_dir / "runtime.json").write_text("{}", encoding="utf-8")
    return project_with_config


# ---------------------------------------------------------------------------
# TestInstallCommand
# ---------------------------------------------------------------------------


class TestInstallCommand:
    """Tests for guard install command."""

    def test_install_no_agent_lists_available(self, tmp_path: Path) -> None:
        """install without --agent lists available agents."""
        config = tmp_path / "guard.yaml"
        config.write_text(
            yaml.dump(
                {"version": 1, "project": {"name": "t", "language": "python"}},
                default_flow_style=False,
            ),
            encoding="utf-8",
        )
        result = runner.invoke(
            app,
            ["install", "--config", str(config)],
        )
        assert result.exit_code == 0
        assert "claude-code" in result.output

    def test_install_single_agent_creates_artifacts(
        self, project_with_config: Path
    ) -> None:
        """install --agent claude-code creates artifacts and state."""
        config = project_with_config / "guard.yaml"
        result = runner.invoke(
            app,
            ["install", "--agent", "claude-code", "--config", str(config)],
        )
        assert result.exit_code == 0
        # State file should exist
        state_path = installation_path(project_with_config)
        assert state_path.is_file()
        state = Installation.from_json(state_path.read_text(encoding="utf-8"))
        assert "claude-code" in state.installed_agents
        # Rule doc should exist
        assert (project_with_config / "CLAUDE.md").is_file()

    def test_install_multiple_agents(self, project_with_config: Path) -> None:
        """install --agent with comma-separated agents installs both."""
        config = project_with_config / "guard.yaml"
        result = runner.invoke(
            app,
            ["install", "--agent", "claude-code,opencode", "--config", str(config)],
        )
        assert result.exit_code == 0
        state_path = installation_path(project_with_config)
        state = Installation.from_json(state_path.read_text(encoding="utf-8"))
        assert "claude-code" in state.installed_agents
        assert "opencode" in state.installed_agents

    def test_install_incremental_appends_agents(self, installed_project: Path) -> None:
        """Second install appends new agent to existing agents."""
        config = installed_project / "guard.yaml"
        result = runner.invoke(
            app,
            ["install", "--agent", "opencode", "--config", str(config)],
        )
        assert result.exit_code == 0
        state_path = installation_path(installed_project)
        state = Installation.from_json(state_path.read_text(encoding="utf-8"))
        assert "claude-code" in state.installed_agents
        assert "opencode" in state.installed_agents

    def test_install_duplicate_agent_is_idempotent(
        self, installed_project: Path
    ) -> None:
        """Installing same agent again doesn't duplicate it."""
        config = installed_project / "guard.yaml"
        result = runner.invoke(
            app,
            ["install", "--agent", "claude-code", "--config", str(config)],
        )
        assert result.exit_code == 0
        state_path = installation_path(installed_project)
        state = Installation.from_json(state_path.read_text(encoding="utf-8"))
        assert state.installed_agents.count("claude-code") == 1

    def test_install_unknown_agent_fails(self, project_with_config: Path) -> None:
        """install with unknown agent name fails with error."""
        config = project_with_config / "guard.yaml"
        result = runner.invoke(
            app,
            ["install", "--agent", "nonexistent", "--config", str(config)],
        )
        assert result.exit_code == 1
        assert "nonexistent" in result.output

    def test_install_no_config_fails(self, tmp_path: Path) -> None:
        """install without guard.yaml fails."""
        config = tmp_path / "guard.yaml"
        result = runner.invoke(
            app,
            ["install", "--agent", "claude-code", "--config", str(config)],
        )
        assert result.exit_code == 1

    def test_install_no_git_dir_warns_continues(self, tmp_path: Path) -> None:
        """install without .git directory warns but continues."""
        config = tmp_path / "guard.yaml"
        config.write_text(
            yaml.dump(
                {"version": 1, "project": {"name": "t", "language": "python"}},
                default_flow_style=False,
            ),
            encoding="utf-8",
        )
        # No .git directory
        result = runner.invoke(
            app,
            ["install", "--agent", "claude-code", "--config", str(config)],
        )
        assert result.exit_code == 0
        assert "Warning" in result.output or "warning" in result.output
        # State should still be created
        state_path = installation_path(tmp_path)
        assert state_path.is_file()

    def test_install_creates_state_json(self, project_with_config: Path) -> None:
        """install creates state.json with correct structure."""
        config = project_with_config / "guard.yaml"
        result = runner.invoke(
            app,
            ["install", "--agent", "claude-code", "--config", str(config)],
        )
        assert result.exit_code == 0
        state_path = installation_path(project_with_config)
        state = Installation.from_json(state_path.read_text(encoding="utf-8"))
        assert state.ac_guard_version
        assert state.config_hash
        assert len(state.artifacts) > 0
        assert state.installed_agents == ["claude-code"]


# ---------------------------------------------------------------------------
# TestUpdateCommand
# ---------------------------------------------------------------------------


class TestUpdateCommand:
    """Tests for guard update command."""

    def test_update_regenerates_artifacts(self, installed_project: Path) -> None:
        """update regenerates artifacts for installed agents."""
        config = installed_project / "guard.yaml"
        result = runner.invoke(
            app,
            ["update", "--config", str(config)],
        )
        assert result.exit_code == 0
        # State should still have claude-code
        state_path = installation_path(installed_project)
        state = Installation.from_json(state_path.read_text(encoding="utf-8"))
        assert "claude-code" in state.installed_agents

    def test_update_no_state_fails(self, project_with_config: Path) -> None:
        """update without prior install fails."""
        config = project_with_config / "guard.yaml"
        result = runner.invoke(
            app,
            ["update", "--config", str(config)],
        )
        assert result.exit_code == 1
        assert "install" in result.output.lower()

    def test_update_reflects_config_changes(self, installed_project: Path) -> None:
        """update picks up config changes (new hash)."""
        config = installed_project / "guard.yaml"
        old_state = Installation.from_json(
            (installation_path(installed_project)).read_text(encoding="utf-8")
        )
        # Modify config
        config.write_text(
            yaml.dump(
                {
                    "version": 1,
                    "project": {"name": "changed", "language": "python"},
                },
                default_flow_style=False,
            ),
            encoding="utf-8",
        )
        result = runner.invoke(
            app,
            ["update", "--config", str(config)],
        )
        assert result.exit_code == 0
        new_state = Installation.from_json(
            (installation_path(installed_project)).read_text(encoding="utf-8")
        )
        assert new_state.config_hash != old_state.config_hash


# ---------------------------------------------------------------------------
# TestUninstallCommand
# ---------------------------------------------------------------------------


class TestUninstallCommand:
    """Tests for guard uninstall command."""

    def test_uninstall_deletes_artifacts(
        self, installed_project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """uninstall deletes generated artifacts."""
        monkeypatch.chdir(installed_project)
        result = runner.invoke(app, ["uninstall"])
        assert result.exit_code == 0
        assert not (installed_project / "CLAUDE.md").exists()
        assert not (installation_path(installed_project)).exists()

    def test_uninstall_no_state_exits_clean(
        self, project_with_config: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """uninstall when nothing is installed exits cleanly."""
        monkeypatch.chdir(project_with_config)
        result = runner.invoke(app, ["uninstall"])
        assert result.exit_code == 0
        assert "Nothing to uninstall" in result.output

    def test_uninstall_keep_config(
        self, installed_project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """uninstall --keep-config preserves guard.yaml."""
        monkeypatch.chdir(installed_project)
        result = runner.invoke(app, ["uninstall", "--keep-config"])
        assert result.exit_code == 0
        assert (installed_project / "guard.yaml").exists()

    def test_uninstall_removes_config(
        self, installed_project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """uninstall without --keep-config removes guard.yaml."""
        monkeypatch.chdir(installed_project)
        result = runner.invoke(app, ["uninstall"])
        assert result.exit_code == 0
        assert not (installed_project / "guard.yaml").exists()

    def test_uninstall_cleans_ac_guard_dir(
        self, installed_project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """uninstall removes .ac-guard/ directory when empty."""
        monkeypatch.chdir(installed_project)
        result = runner.invoke(app, ["uninstall"])
        assert result.exit_code == 0
        assert not (installed_project / ".ac-guard").exists()
