"""Tests for init command."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from typer.testing import CliRunner

from ac_guard import __version__
from ac_guard.cli.init import (
    _get_jinja_env,
    _get_project_name,
    _merge_config,
    _render_guard_yaml,
)
from ac_guard.cli.main import app
from ac_guard.cli.presets import load_preset

runner = CliRunner()


class TestInitCommand:
    """Tests for init command CLI interface."""

    def test_init_creates_guard_yaml(self, tmp_path: Path) -> None:
        """init command creates guard.yaml file."""
        output = tmp_path / "guard.yaml"
        result = runner.invoke(
            app,
            ["init", "--language", "python", "--output", str(output)],
        )
        assert result.exit_code == 0
        assert output.exists()

    def test_init_with_language(self, tmp_path: Path) -> None:
        """init command with --language parameter."""
        output = tmp_path / "guard.yaml"
        result = runner.invoke(
            app,
            ["init", "--language", "typescript", "--output", str(output)],
        )
        assert result.exit_code == 0
        content = output.read_text()
        assert "language: typescript" in content

    def test_init_with_preset(self, tmp_path: Path) -> None:
        """init command with --preset parameter."""
        output = tmp_path / "guard.yaml"
        result = runner.invoke(
            app,
            [
                "init",
                "--language",
                "python",
                "--preset",
                "minimal",
                "--output",
                str(output),
            ],
        )
        assert result.exit_code == 0
        content = output.read_text()
        assert "Preset: minimal" in content

    def test_init_with_ruleset(self, tmp_path: Path) -> None:
        """init command with --ruleset parameter."""
        output = tmp_path / "guard.yaml"
        result = runner.invoke(
            app,
            [
                "init",
                "--language",
                "python",
                "--ruleset",
                "security-rules",
                "--output",
                str(output),
            ],
        )
        assert result.exit_code == 0
        content = output.read_text()
        assert "security-rules" in content

    def test_init_multiple_rulesets(self, tmp_path: Path) -> None:
        """init command with multiple --ruleset parameters."""
        output = tmp_path / "guard.yaml"
        result = runner.invoke(
            app,
            [
                "init",
                "--language",
                "python",
                "--ruleset",
                "security-rules",
                "--ruleset",
                "team-conventions",
                "--output",
                str(output),
            ],
        )
        assert result.exit_code == 0
        content = output.read_text()
        assert "security-rules" in content
        assert "team-conventions" in content

    def test_init_existing_file_fails(self, tmp_path: Path) -> None:
        """init command fails when guard.yaml already exists."""
        output = tmp_path / "guard.yaml"
        output.write_text("existing content")
        result = runner.invoke(
            app,
            ["init", "--language", "python", "--output", str(output)],
        )
        assert result.exit_code == 1
        assert "already exists" in result.output

    def test_init_force_overwrites(self, tmp_path: Path) -> None:
        """init --force overwrites existing guard.yaml."""
        output = tmp_path / "guard.yaml"
        output.write_text("existing content")
        result = runner.invoke(
            app,
            ["init", "--language", "python", "--force", "--output", str(output)],
        )
        assert result.exit_code == 0
        content = output.read_text()
        assert "existing content" not in content
        assert "AI Code Guard configuration" in content

    def test_init_custom_output_path(self, tmp_path: Path) -> None:
        """init command with custom output path."""
        output = tmp_path / "custom" / "my-guard.yaml"
        output.parent.mkdir(parents=True)
        result = runner.invoke(
            app,
            ["init", "--language", "python", "--output", str(output)],
        )
        assert result.exit_code == 0
        assert output.exists()

    def test_init_unknown_preset_fails(self, tmp_path: Path) -> None:
        """init command with unknown preset fails."""
        output = tmp_path / "guard.yaml"
        result = runner.invoke(
            app,
            [
                "init",
                "--language",
                "python",
                "--preset",
                "unknown",
                "--output",
                str(output),
            ],
        )
        assert result.exit_code == 1
        assert "Unknown preset" in result.output


class TestGetProjectName:
    """Tests for _get_project_name function."""

    def test_get_project_name_returns_directory_name(self, tmp_path: Path) -> None:
        """_get_project_name returns current directory name."""
        # This test checks the function behavior relative to cwd
        name = _get_project_name()
        assert isinstance(name, str)
        assert len(name) > 0

    def test_get_project_name_is_string(self) -> None:
        """_get_project_name returns a string."""
        name = _get_project_name()
        assert isinstance(name, str)


class TestMergeConfig:
    """Tests for _merge_config function."""

    def test_merge_config_basic(self) -> None:
        """_merge_config merges basic parameters."""
        preset_config = load_preset("standard")
        merged = _merge_config(
            preset_config,
            language="python",
            rulesets=["security-rules"],
            project_name="my-project",
        )
        assert merged["project"]["name"] == "my-project"
        assert merged["project"]["language"] == "python"
        assert merged["rulesets"] == ["security-rules"]

    def test_merge_config_no_rulesets(self) -> None:
        """_merge_config handles empty rulesets."""
        preset_config = load_preset("minimal")
        merged = _merge_config(
            preset_config,
            language="go",
            rulesets=[],
            project_name="test-project",
        )
        # Empty rulesets should not be added
        assert "rulesets" not in merged or merged.get("rulesets") == []

    def test_merge_config_preserves_preset_code(self) -> None:
        """_merge_config preserves preset's code configuration."""
        preset_config = load_preset("strict")
        merged = _merge_config(
            preset_config,
            language="rust",
            rulesets=["team-rules"],
            project_name="rust-project",
        )
        # strict preset has behavior.write.forbidden
        assert "behavior" in merged
        assert "write" in merged["behavior"]
        assert len(merged["behavior"]["write"]["forbidden"]) > 0

    def test_merge_config_adds_version_if_missing(self) -> None:
        """_merge_config adds version field if not in preset."""
        preset_config: dict[str, Any] = {}
        merged = _merge_config(
            preset_config,
            language="python",
            rulesets=[],
            project_name="test",
        )
        assert merged["version"] == 1

    def test_merge_config_preserves_existing_version(self) -> None:
        """_merge_config preserves preset's version."""
        preset_config = {"version": 2, "code": {}}
        merged = _merge_config(
            preset_config,
            language="python",
            rulesets=[],
            project_name="test",
        )
        assert merged["version"] == 2


class TestRenderGuardYaml:
    """Tests for _render_guard_yaml function."""

    def test_render_guard_yaml_contains_version(self) -> None:
        """_render_guard_yaml contains version info in header."""
        config = {
            "version": 1,
            "project": {"name": "test", "language": "python"},
        }
        yaml_content = _render_guard_yaml(config, "standard")
        assert __version__ in yaml_content

    def test_render_guard_yaml_contains_preset(self) -> None:
        """_render_guard_yaml contains preset name in header."""
        config = {
            "version": 1,
            "project": {"name": "test", "language": "python"},
        }
        yaml_content = _render_guard_yaml(config, "minimal")
        assert "Preset: minimal" in yaml_content

    def test_render_guard_yaml_valid_yaml(self) -> None:
        """_render_guard_yaml produces valid YAML."""
        config = load_preset("standard")
        config["project"] = {"name": "test", "language": "python"}
        yaml_content = _render_guard_yaml(config, "standard")
        # Remove comment lines for parsing
        lines = [
            line
            for line in yaml_content.split("\n")
            if not line.strip().startswith("#")
        ]
        clean_yaml = "\n".join(lines)
        parsed = yaml.safe_load(clean_yaml)
        assert parsed is not None
        assert parsed["project"]["language"] == "python"

    def test_render_guard_yaml_no_duplicate_project(self) -> None:
        """_render_guard_yaml does not duplicate project section."""
        config = {
            "version": 1,
            "project": {"name": "test", "language": "python"},
            "code": {"commit": {"format": True}},
        }
        yaml_content = _render_guard_yaml(config, "standard")
        # Count occurrences of "project:" (should be exactly 1)
        project_count = yaml_content.count("project:")
        assert project_count == 1


class TestGetJinjaEnv:
    """Tests for _get_jinja_env function."""

    def test_get_jinja_env_returns_environment(self) -> None:
        """_get_jinja_env returns a Jinja2 Environment."""
        env = _get_jinja_env()
        assert env is not None
        from jinja2 import Environment

        assert isinstance(env, Environment)

    def test_get_jinja_env_singleton(self) -> None:
        """_get_jinja_env returns the same instance on repeated calls."""
        env1 = _get_jinja_env()
        env2 = _get_jinja_env()
        assert env1 is env2


class TestInitCommandIntegration:
    """Integration tests for init command."""

    def test_init_standard_preset_yaml_content(self, tmp_path: Path) -> None:
        """init standard preset produces expected YAML content."""
        output = tmp_path / "guard.yaml"
        result = runner.invoke(
            app,
            [
                "init",
                "--language",
                "python",
                "--preset",
                "standard",
                "--output",
                str(output),
            ],
        )
        assert result.exit_code == 0

        content = output.read_text()
        # Check for expected content from standard preset
        assert "format: true" in content
        assert "lint: true" in content
        assert "audit:" in content
        assert "enabled: true" in content
        # naming shortcut is not shipped with the preset — see #95
        assert "naming" not in content

    def test_init_strict_preset_yaml_content(self, tmp_path: Path) -> None:
        """init strict preset produces expected YAML content."""
        output = tmp_path / "guard.yaml"
        result = runner.invoke(
            app,
            [
                "init",
                "--language",
                "python",
                "--preset",
                "strict",
                "--output",
                str(output),
            ],
        )
        assert result.exit_code == 0

        content = output.read_text()
        # Check for expected content from strict preset
        assert "behavior:" in content
        assert "forbidden:" in content
        assert ".env" in content
        assert "pr_report:" in content

    def test_init_minimal_preset_yaml_content(self, tmp_path: Path) -> None:
        """init minimal preset produces expected YAML content."""
        output = tmp_path / "guard.yaml"
        result = runner.invoke(
            app,
            [
                "init",
                "--language",
                "python",
                "--preset",
                "minimal",
                "--output",
                str(output),
            ],
        )
        assert result.exit_code == 0

        content = output.read_text()
        # Check minimal preset specific content
        assert "format: true" in content
        assert "enabled: false" in content  # audit disabled
