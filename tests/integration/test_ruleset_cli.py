"""Integration tests for ruleset CLI commands (WP4.1).

Verifies the complete ruleset management flow:
    guard ruleset fetch → list → cache clear

Uses real git repos and file I/O (no mocks), following the
project's integration test patterns.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import yaml
from typer.testing import CliRunner

from ai_guard.cli.main import app
from ai_guard.generator.models import STATE_FILE

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_bare_repo(
    base: Path,
    name: str = "test-rules",
    *,
    guard_yaml_content: dict | None = None,
    tag: str | None = None,
) -> str:
    """Create a local bare git repo and return a file:// URL."""
    base.mkdir(parents=True, exist_ok=True)
    work = base / f"{name}-work"
    bare = base / f"{name}.git"
    work.mkdir()
    bare.mkdir()

    subprocess.run(
        ["git", "init", "--bare", str(bare)], check=True, capture_output=True
    )
    subprocess.run(
        ["git", "clone", str(bare), str(work)], check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=work,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=work,
        check=True,
        capture_output=True,
    )

    content = guard_yaml_content or {
        "behavior": {
            "read": {
                "forbidden": [{"pattern": "file:secret/**", "reason": "no secrets"}]
            },
        },
    }
    (work / "guard.yaml").write_text(yaml.dump(content), encoding="utf-8")

    (work / "files").mkdir()
    (work / "files" / ".editorconfig").write_text("root = true\n", encoding="utf-8")
    (work / "checks").mkdir()
    (work / "checks" / "check_headers.py").write_text("# check\n", encoding="utf-8")

    subprocess.run(["git", "add", "."], cwd=work, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"], cwd=work, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "push", "origin", "HEAD"], cwd=work, check=True, capture_output=True
    )

    if tag:
        subprocess.run(["git", "tag", tag], cwd=work, check=True, capture_output=True)
        subprocess.run(
            ["git", "push", "origin", tag], cwd=work, check=True, capture_output=True
        )

    return bare.as_uri()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRulesetFetchAndCacheClear:
    """Test guard ruleset fetch → list → cache clear lifecycle."""

    def test_fetch_list_clear(self, tmp_path: Path) -> None:
        """Full lifecycle: fetch a ruleset, list it, then clear cache."""
        url = _create_bare_repo(tmp_path / "repos")
        pr = str(tmp_path)

        # fetch
        result = runner.invoke(app, ["ruleset", "fetch", url, "--project-root", pr])
        assert result.exit_code == 0, f"fetch failed: {result.output}"
        assert "Fetching ruleset" in result.output
        assert "guard.yaml: found" in result.output

        # Verify cache populated
        cache_dir = tmp_path / ".ai-guard" / "cache" / "test-rules"
        assert cache_dir.is_dir()
        assert (cache_dir / "guard.yaml").is_file()
        assert (cache_dir / ".ruleset-meta.json").is_file()

        # list
        result = runner.invoke(app, ["ruleset", "list", "--project-root", pr])
        assert result.exit_code == 0
        assert "test-rules" in result.output

        # cache clear
        result = runner.invoke(app, ["ruleset", "cache", "clear", "--project-root", pr])
        assert result.exit_code == 0
        assert "Cleared 1" in result.output

        # list again (empty)
        result = runner.invoke(app, ["ruleset", "list", "--project-root", pr])
        assert result.exit_code == 0
        assert "No cached rulesets" in result.output

    def test_fetch_with_tag(self, tmp_path: Path) -> None:
        """Fetch a specific version using #tag."""
        url = _create_bare_repo(tmp_path / "repos", tag="v1.0")
        pr = str(tmp_path)

        result = runner.invoke(
            app, ["ruleset", "fetch", f"{url}#v1.0", "--project-root", pr]
        )
        assert result.exit_code == 0, f"fetch failed: {result.output}"
        assert "v1.0" in result.output

    def test_fetch_invalid_url(self, tmp_path: Path) -> None:
        """Fetch with invalid URL shows error."""
        result = runner.invoke(
            app, ["ruleset", "fetch", "not-a-url", "--project-root", str(tmp_path)]
        )
        assert result.exit_code == 1
        assert "Error" in result.output


class TestInstallWithRuleset:
    """Test that install merges ruleset config from cache."""

    def test_install_loads_ruleset_config(self, tmp_path: Path) -> None:
        """fetch → init (with ruleset name) → install → verify merge."""
        (tmp_path / ".git").mkdir()
        pr = str(tmp_path)

        # Create a ruleset with a custom rule
        ruleset_config = {
            "behavior": {
                "read": {
                    "forbidden": [
                        {"pattern": "file:.env*", "reason": "env files forbidden"},
                    ],
                },
            },
        }
        url = _create_bare_repo(
            tmp_path / "repos",
            name="company-rules",
            guard_yaml_content=ruleset_config,
        )

        # Fetch the ruleset
        result = runner.invoke(app, ["ruleset", "fetch", url, "--project-root", pr])
        assert result.exit_code == 0, f"fetch failed: {result.output}"

        # Use guard init to create a valid guard.yaml, then add rulesets
        config_path = tmp_path / "guard.yaml"
        result = runner.invoke(
            app,
            ["init", "--language", "python", "--output", str(config_path)],
        )
        assert result.exit_code == 0, f"init failed: {result.output}"

        # Append rulesets field to the config
        text = config_path.read_text(encoding="utf-8")
        text += '\nrulesets:\n  - "company-rules"\n'
        config_path.write_text(text, encoding="utf-8")

        # Install
        result = runner.invoke(
            app,
            ["install", "--agent", "claude-code", "--config", str(config_path)],
        )
        assert result.exit_code == 0, f"install failed: {result.output}"

        # Verify state was written
        state_path = tmp_path / STATE_FILE
        assert state_path.is_file()

        # Verify the ruleset's .editorconfig was copied via G3
        assert (tmp_path / ".editorconfig").is_file()

    def test_install_warns_missing_ruleset(self, tmp_path: Path) -> None:
        """install with uncached ruleset should warn."""
        (tmp_path / ".git").mkdir()

        # Use guard init to create a valid guard.yaml
        config_path = tmp_path / "guard.yaml"
        result = runner.invoke(
            app,
            ["init", "--language", "python", "--output", str(config_path)],
        )
        assert result.exit_code == 0

        # Add a non-existent ruleset reference
        text = config_path.read_text(encoding="utf-8")
        text += '\nrulesets:\n  - "nonexistent-rules"\n'
        config_path.write_text(text, encoding="utf-8")

        result = runner.invoke(
            app,
            ["install", "--agent", "claude-code", "--config", str(config_path)],
        )
        assert result.exit_code == 0
        assert "Warning" in result.output
        assert "nonexistent-rules" in result.output


class TestRulesetFileCopy:
    """Test ruleset files/ and checks/ copying (WP4.2)."""

    def _init_and_install_with_ruleset(
        self,
        tmp_path: Path,
        ruleset_url: str,
        ruleset_name: str,
        extra_args: list[str] | None = None,
    ) -> object:
        """Helper: fetch ruleset, init config, install."""
        pr = str(tmp_path)
        (tmp_path / ".git").mkdir(exist_ok=True)

        # Fetch
        result = runner.invoke(
            app, ["ruleset", "fetch", ruleset_url, "--project-root", pr]
        )
        assert result.exit_code == 0, f"fetch failed: {result.output}"

        # Init config
        config_path = tmp_path / "guard.yaml"
        if not config_path.is_file():
            result = runner.invoke(
                app, ["init", "--language", "python", "--output", str(config_path)]
            )
            assert result.exit_code == 0

        # Add rulesets
        text = config_path.read_text(encoding="utf-8")
        if "rulesets:" not in text:
            text += f'\nrulesets:\n  - "{ruleset_name}"\n'
            config_path.write_text(text, encoding="utf-8")

        # Install
        cmd = ["install", "--agent", "claude-code", "--config", str(config_path)]
        if extra_args:
            cmd.extend(extra_args)
        return runner.invoke(app, cmd)

    def test_install_copies_checks_to_ai_guard(self, tmp_path: Path) -> None:
        """Check scripts from ruleset should appear in .ai-guard/checks/."""
        url = _create_bare_repo(tmp_path / "repos")
        result = self._init_and_install_with_ruleset(tmp_path, url, "test-rules")
        assert result.exit_code == 0, f"install failed: {result.output}"
        assert (tmp_path / ".ai-guard" / "checks" / "check_headers.py").is_file()

    def test_install_copies_files_to_root(self, tmp_path: Path) -> None:
        """Tool config files from ruleset should appear at project root."""
        url = _create_bare_repo(tmp_path / "repos")
        result = self._init_and_install_with_ruleset(tmp_path, url, "test-rules")
        assert result.exit_code == 0, f"install failed: {result.output}"
        assert (tmp_path / ".editorconfig").is_file()
        assert (tmp_path / ".editorconfig").read_text(
            encoding="utf-8"
        ) == "root = true\n"

    def test_install_skips_existing_files(self, tmp_path: Path) -> None:
        """Existing user files should not be overwritten without --force."""
        url = _create_bare_repo(tmp_path / "repos")

        # Create user file BEFORE install
        (tmp_path / ".editorconfig").write_text("user content", encoding="utf-8")

        result = self._init_and_install_with_ruleset(tmp_path, url, "test-rules")
        assert result.exit_code == 0
        assert "Skipping" in result.output or "skip" in result.output.lower()

        # User file should be preserved
        assert (tmp_path / ".editorconfig").read_text(
            encoding="utf-8"
        ) == "user content"

    def test_install_force_overwrites_existing_files(self, tmp_path: Path) -> None:
        """--force should overwrite existing user files."""
        url = _create_bare_repo(tmp_path / "repos")

        # Create user file BEFORE install
        (tmp_path / ".editorconfig").write_text("user content", encoding="utf-8")

        result = self._init_and_install_with_ruleset(
            tmp_path, url, "test-rules", extra_args=["--force"]
        )
        assert result.exit_code == 0

        # Ruleset file should have replaced user file
        assert (tmp_path / ".editorconfig").read_text(
            encoding="utf-8"
        ) == "root = true\n"
