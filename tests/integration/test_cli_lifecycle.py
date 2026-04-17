"""Integration tests for Phase 1 CLI lifecycle (WP1.6).

Verifies the complete flow:
    guard init → install → status → agents → doctor → update → uninstall

Each test class covers one lifecycle scenario end-to-end, using a real
temporary directory with actual file I/O (no mocks).
"""

from __future__ import annotations

from pathlib import Path

import yaml
from typer.testing import CliRunner

from ac_guard.cli.main import app
from ac_guard.generator.models import STATE_FILE, GeneratedState

runner = CliRunner()


class TestFullLifecycle:
    """Full init → install → status → agents → doctor → update → uninstall."""

    def test_complete_lifecycle(self, tmp_path: Path) -> None:
        """Run the entire CLI lifecycle in sequence."""
        config = tmp_path / "guard.yaml"
        (tmp_path / ".git").mkdir()

        # 1. init
        result = runner.invoke(
            app,
            ["init", "--language", "python", "--output", str(config)],
        )
        assert result.exit_code == 0, f"init failed: {result.output}"
        assert config.is_file()

        # 2. install --agent claude-code
        result = runner.invoke(
            app,
            ["install", "--agent", "claude-code", "--config", str(config)],
        )
        assert result.exit_code == 0, f"install failed: {result.output}"
        state_path = tmp_path / STATE_FILE
        assert state_path.is_file()
        state = GeneratedState.from_json(state_path.read_text())
        assert "claude-code" in state.installed_agents
        assert (tmp_path / "CLAUDE.md").is_file()

        # 3. status
        result = runner.invoke(
            app,
            ["status", "--config", str(config)],
        )
        assert result.exit_code == 0, f"status failed: {result.output}"
        assert "claude-code" in result.output
        assert "up to date" in result.output.lower()

        # 4. status --rules
        result = runner.invoke(
            app,
            ["status", "--rules", "--config", str(config)],
        )
        assert result.exit_code == 0, f"status --rules failed: {result.output}"
        assert "rule" in result.output.lower()

        # 5. agents
        result = runner.invoke(app, ["agents"])
        assert result.exit_code == 0, f"agents failed: {result.output}"
        assert "claude-code" in result.output.lower()

        # 6. doctor
        result = runner.invoke(
            app,
            ["doctor", "--config", str(config)],
        )
        assert result.exit_code == 0, f"doctor failed: {result.output}"
        assert "python" in result.output.lower()

        # 7. update (no config change — should still succeed)
        result = runner.invoke(
            app,
            ["update", "--config", str(config)],
        )
        assert result.exit_code == 0, f"update failed: {result.output}"

        # 8. uninstall --keep-config
        result = runner.invoke(
            app,
            ["uninstall", "--keep-config"],
        )
        # uninstall uses cwd, but our state is in tmp_path
        # Use monkeypatch approach via separate test below

    def test_uninstall_lifecycle(self, tmp_path: Path, monkeypatch: object) -> None:
        """Test uninstall as part of lifecycle (requires chdir)."""
        import pytest

        mp = pytest.MonkeyPatch()
        config = tmp_path / "guard.yaml"
        (tmp_path / ".git").mkdir()

        # init + install
        runner.invoke(app, ["init", "--language", "python", "--output", str(config)])
        runner.invoke(
            app, ["install", "--agent", "claude-code", "--config", str(config)]
        )
        assert (tmp_path / STATE_FILE).is_file()

        # uninstall --keep-config
        mp.chdir(tmp_path)
        result = runner.invoke(app, ["uninstall", "--keep-config"])
        assert result.exit_code == 0, f"uninstall failed: {result.output}"
        assert not (tmp_path / STATE_FILE).exists()
        assert config.is_file()  # guard.yaml preserved
        mp.undo()


class TestMultiAgentLifecycle:
    """Multi-agent installation and incremental install flow."""

    def test_incremental_install(self, tmp_path: Path) -> None:
        """Install agents incrementally, then update and uninstall."""
        config = tmp_path / "guard.yaml"
        (tmp_path / ".git").mkdir()

        # init
        runner.invoke(app, ["init", "--language", "python", "--output", str(config)])

        # install first agent
        result = runner.invoke(
            app,
            ["install", "--agent", "claude-code", "--config", str(config)],
        )
        assert result.exit_code == 0
        state = GeneratedState.from_json((tmp_path / STATE_FILE).read_text())
        assert state.installed_agents == ["claude-code"]

        # install second agent (incremental)
        result = runner.invoke(
            app,
            ["install", "--agent", "cursor", "--config", str(config)],
        )
        assert result.exit_code == 0
        state = GeneratedState.from_json((tmp_path / STATE_FILE).read_text())
        assert "claude-code" in state.installed_agents
        assert "cursor" in state.installed_agents

        # status should show both agents
        result = runner.invoke(app, ["status", "--config", str(config)])
        assert "claude-code" in result.output
        assert "cursor" in result.output

        # update regenerates for both
        result = runner.invoke(app, ["update", "--config", str(config)])
        assert result.exit_code == 0
        assert "claude-code" in result.output
        assert "cursor" in result.output

    def test_comma_separated_install(self, tmp_path: Path) -> None:
        """Install multiple agents at once with comma-separated list."""
        config = tmp_path / "guard.yaml"
        (tmp_path / ".git").mkdir()

        runner.invoke(app, ["init", "--language", "python", "--output", str(config)])

        result = runner.invoke(
            app,
            [
                "install",
                "--agent",
                "claude-code,cursor,copilot",
                "--config",
                str(config),
            ],
        )
        assert result.exit_code == 0
        state = GeneratedState.from_json((tmp_path / STATE_FILE).read_text())
        assert len(state.installed_agents) == 3
        assert "claude-code" in state.installed_agents
        assert "cursor" in state.installed_agents
        assert "copilot" in state.installed_agents


class TestDriftDetection:
    """Configuration drift detection end-to-end."""

    def test_drift_detect_and_resolve(self, tmp_path: Path) -> None:
        """Modify guard.yaml → status warns → update resolves."""
        config = tmp_path / "guard.yaml"
        (tmp_path / ".git").mkdir()

        # init + install
        runner.invoke(app, ["init", "--language", "python", "--output", str(config)])
        runner.invoke(
            app, ["install", "--agent", "claude-code", "--config", str(config)]
        )

        # Verify no drift initially
        result = runner.invoke(app, ["status", "--config", str(config)])
        assert "up to date" in result.output.lower()

        # Modify guard.yaml to create drift
        config.write_text(
            yaml.dump(
                {
                    "version": 1,
                    "project": {"name": "modified", "language": "python"},
                    "behavior": {
                        "write": {
                            "forbidden": [
                                {"pattern": "file:.env", "reason": "no secrets"}
                            ]
                        }
                    },
                },
                default_flow_style=False,
            ),
        )

        # Status should detect drift
        result = runner.invoke(app, ["status", "--config", str(config)])
        assert "drift" in result.output.lower()

        # Update resolves drift
        result = runner.invoke(app, ["update", "--config", str(config)])
        assert result.exit_code == 0

        # Status should show no drift now
        result = runner.invoke(app, ["status", "--config", str(config)])
        assert "up to date" in result.output.lower()


class TestErrorRecovery:
    """Error handling and edge cases."""

    def test_install_without_init(self, tmp_path: Path) -> None:
        """install without guard.yaml fails gracefully."""
        config = tmp_path / "guard.yaml"
        result = runner.invoke(
            app,
            ["install", "--agent", "claude-code", "--config", str(config)],
        )
        assert result.exit_code == 1

    def test_update_without_install(self, tmp_path: Path) -> None:
        """update without prior install fails gracefully."""
        config = tmp_path / "guard.yaml"
        config.write_text(
            yaml.dump(
                {"version": 1, "project": {"name": "t", "language": "python"}},
                default_flow_style=False,
            ),
        )
        result = runner.invoke(app, ["update", "--config", str(config)])
        assert result.exit_code == 1
        assert "install" in result.output.lower()

    def test_install_unknown_agent(self, tmp_path: Path) -> None:
        """install with invalid agent name fails with helpful message."""
        config = tmp_path / "guard.yaml"
        config.write_text(
            yaml.dump(
                {"version": 1, "project": {"name": "t", "language": "python"}},
                default_flow_style=False,
            ),
        )
        result = runner.invoke(
            app,
            ["install", "--agent", "does-not-exist", "--config", str(config)],
        )
        assert result.exit_code == 1
        assert "does-not-exist" in result.output

    def test_status_without_install(self, tmp_path: Path) -> None:
        """status without install shows not-installed message."""
        config = tmp_path / "guard.yaml"
        config.write_text(
            yaml.dump(
                {"version": 1, "project": {"name": "t", "language": "python"}},
                default_flow_style=False,
            ),
        )
        result = runner.invoke(app, ["status", "--config", str(config)])
        assert result.exit_code == 0
        assert "not installed" in result.output.lower()

    def test_install_without_git_continues(self, tmp_path: Path) -> None:
        """install without .git warns but succeeds."""
        config = tmp_path / "guard.yaml"
        config.write_text(
            yaml.dump(
                {"version": 1, "project": {"name": "t", "language": "python"}},
                default_flow_style=False,
            ),
        )
        result = runner.invoke(
            app,
            ["install", "--agent", "claude-code", "--config", str(config)],
        )
        assert result.exit_code == 0
        assert "warning" in result.output.lower()
        assert (tmp_path / STATE_FILE).is_file()
