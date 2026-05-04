"""Integration tests for M4 Ruleset lifecycle (WP4.4).

Verifies Ruleset management end-to-end across four dimensions:
    D1: Lifecycle stages (fetch → install → update → uninstall)
    D2: Rule merging correctness (Action guard evaluates ruleset rules)
    D3: File copy completeness (files/ and checks/ survive update)
    D4: Multi-ruleset interaction (merge order, file aggregation)
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from ac_guard.action_guard.engine import evaluate
from ac_guard.action_guard.matcher import Decision
from ac_guard.cli.main import app
from ac_guard.generator import installation_path

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_bare_repo(
    base: Path,
    name: str = "test-rules",
    *,
    guard_yaml_content: dict | None = None,
    files: dict[str, str] | None = None,
    checks: dict[str, str] | None = None,
) -> str:
    """Create a local bare git repo and return a file:// URL.

    Args:
        base: Parent directory for the repo.
        name: Repo directory name.
        guard_yaml_content: Custom guard.yaml content dict.
        files: Mapping of filename → content for files/ directory.
        checks: Mapping of filename → content for checks/ directory.

    Returns:
        file:// URL pointing to the bare repo.
    """
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

    content = guard_yaml_content or {}
    (work / "guard.yaml").write_text(yaml.dump(content), encoding="utf-8")

    # files/
    files_data = files or {}
    if files_data:
        (work / "files").mkdir()
        for fname, fcontent in files_data.items():
            (work / "files" / fname).write_text(fcontent, encoding="utf-8")

    # checks/
    checks_data = checks or {}
    if checks_data:
        (work / "checks").mkdir()
        for cname, ccontent in checks_data.items():
            (work / "checks" / cname).write_text(ccontent, encoding="utf-8")

    subprocess.run(["git", "add", "."], cwd=work, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"], cwd=work, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "push", "origin", "HEAD"], cwd=work, check=True, capture_output=True
    )

    return bare.as_uri()


def _init_config(tmp_path: Path, rulesets: list[str] | None = None) -> Path:
    """Create guard.yaml via CLI init, optionally adding rulesets."""
    config_path = tmp_path / "guard.yaml"
    result = runner.invoke(
        app, ["init", "--language", "python", "--output", str(config_path)]
    )
    assert result.exit_code == 0, f"init failed: {result.output}"

    if rulesets:
        text = config_path.read_text(encoding="utf-8")
        rs_yaml = "\nrulesets:\n" + "".join(f'  - "{r}"\n' for r in rulesets)
        config_path.write_text(text + rs_yaml, encoding="utf-8")

    return config_path


def _fetch(tmp_path: Path, url: str) -> None:
    """Fetch a ruleset into tmp_path cache."""
    result = runner.invoke(
        app, ["ruleset", "fetch", url, "--project-root", str(tmp_path)]
    )
    assert result.exit_code == 0, f"fetch failed: {result.output}"


# ---------------------------------------------------------------------------
# D1: Lifecycle Stages
# ---------------------------------------------------------------------------


class TestLifecycleStages:
    """D1: Full lifecycle transitions."""

    def test_fetch_install_update_uninstall(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """D1-1: Complete lifecycle — fetch → install → update → uninstall."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".git").mkdir()
        url = _create_bare_repo(
            tmp_path / "repos",
            files={".editorconfig": "root = true\n"},
            checks={"check_header.py": "# header check\n"},
        )

        # fetch
        _fetch(tmp_path, url)
        assert (
            tmp_path / ".ac-guard" / "cache" / "test-rules" / "guard.yaml"
        ).is_file()

        # install
        config = _init_config(tmp_path, rulesets=["test-rules"])
        result = runner.invoke(
            app, ["install", "--agent", "claude-code", "--config", str(config)]
        )
        assert result.exit_code == 0, f"install failed: {result.output}"
        assert (installation_path(tmp_path)).is_file()
        assert (tmp_path / ".editorconfig").is_file()
        assert (tmp_path / ".ac-guard" / "checks" / "check_header.py").is_file()

        # update
        result = runner.invoke(app, ["update", "--config", str(config)])
        assert result.exit_code == 0, f"update failed: {result.output}"

        # uninstall (uses cwd, hence monkeypatch.chdir)
        result = runner.invoke(app, ["uninstall"])
        assert result.exit_code == 0, f"uninstall failed: {result.output}"
        assert not (installation_path(tmp_path)).is_file()

    def test_fetch_clear_refetch(self, tmp_path: Path) -> None:
        """D1-2: Cache recovery — fetch → clear → re-fetch → install."""
        (tmp_path / ".git").mkdir()
        pr = str(tmp_path)
        url = _create_bare_repo(
            tmp_path / "repos",
            files={".editorconfig": "root = true\n"},
        )

        # fetch
        _fetch(tmp_path, url)
        assert (tmp_path / ".ac-guard" / "cache" / "test-rules").is_dir()

        # clear
        result = runner.invoke(app, ["ruleset", "cache", "clear", "--project-root", pr])
        assert result.exit_code == 0
        assert not (tmp_path / ".ac-guard" / "cache" / "test-rules").is_dir()

        # re-fetch
        _fetch(tmp_path, url)
        assert (tmp_path / ".ac-guard" / "cache" / "test-rules").is_dir()

        # install should work after re-fetch
        config = _init_config(tmp_path, rulesets=["test-rules"])
        result = runner.invoke(
            app, ["install", "--agent", "claude-code", "--config", str(config)]
        )
        assert result.exit_code == 0, f"install after re-fetch failed: {result.output}"
        assert (tmp_path / ".editorconfig").is_file()


# ---------------------------------------------------------------------------
# D2: Rule Merging Correctness
# ---------------------------------------------------------------------------


class TestRuleMergingCorrectness:
    """D2: Action guard evaluates ruleset rules correctly."""

    def test_ruleset_rule_enforced(self, tmp_path: Path) -> None:
        """D2-1: Ruleset adds read.forbidden → Action guard denies."""
        (tmp_path / ".git").mkdir()
        url = _create_bare_repo(
            tmp_path / "repos",
            guard_yaml_content={
                "behavior": {
                    "read": {
                        "forbidden": [{"pattern": "file:.env*", "reason": "secrets"}],
                    },
                },
            },
        )

        _fetch(tmp_path, url)
        config = _init_config(tmp_path, rulesets=["test-rules"])
        runner.invoke(
            app, ["install", "--agent", "claude-code", "--config", str(config)]
        )

        result = evaluate("Read", {"file_path": ".env.local"}, tmp_path)
        assert result.decision == Decision.DENY

    def test_no_ruleset_allows_same_operation(self, tmp_path: Path) -> None:
        """D2-2: Without ruleset, same operation is allowed."""
        (tmp_path / ".git").mkdir()
        config = _init_config(tmp_path)
        runner.invoke(
            app, ["install", "--agent", "claude-code", "--config", str(config)]
        )

        result = evaluate("Read", {"file_path": ".env.local"}, tmp_path)
        assert result.decision == Decision.ALLOW

    def test_update_applies_new_ruleset_rules(self, tmp_path: Path) -> None:
        """D2-3: Adding ruleset after install → update reflects new rules."""
        (tmp_path / ".git").mkdir()
        url = _create_bare_repo(
            tmp_path / "repos",
            guard_yaml_content={
                "behavior": {
                    "read": {
                        "forbidden": [{"pattern": "file:*.secret", "reason": "no"}],
                    },
                },
            },
        )

        # Install WITHOUT ruleset
        config = _init_config(tmp_path)
        runner.invoke(
            app, ["install", "--agent", "claude-code", "--config", str(config)]
        )
        result = evaluate("Read", {"file_path": "key.secret"}, tmp_path)
        assert result.decision == Decision.ALLOW

        # Fetch ruleset, add to config, update
        _fetch(tmp_path, url)
        text = config.read_text(encoding="utf-8")
        text += '\nrulesets:\n  - "test-rules"\n'
        config.write_text(text, encoding="utf-8")

        runner.invoke(app, ["update", "--config", str(config)])

        # Now should be denied
        result = evaluate("Read", {"file_path": "key.secret"}, tmp_path)
        assert result.decision == Decision.DENY


# ---------------------------------------------------------------------------
# D3: File Copy Completeness
# ---------------------------------------------------------------------------


class TestFileCopyCompleteness:
    """D3: Files and checks survive update, cleaned on uninstall."""

    def test_files_persist_after_update(self, tmp_path: Path) -> None:
        """D3-1: files/ and checks/ still present after update."""
        (tmp_path / ".git").mkdir()
        url = _create_bare_repo(
            tmp_path / "repos",
            files={".editorconfig": "root = true\n"},
            checks={"lint.py": "# lint\n"},
        )

        _fetch(tmp_path, url)
        config = _init_config(tmp_path, rulesets=["test-rules"])

        # Install
        runner.invoke(
            app, ["install", "--agent", "claude-code", "--config", str(config)]
        )
        assert (tmp_path / ".editorconfig").is_file()
        assert (tmp_path / ".ac-guard" / "checks" / "lint.py").is_file()

        # Update
        result = runner.invoke(app, ["update", "--config", str(config)])
        assert result.exit_code == 0

        # Files should still be there
        assert (tmp_path / ".editorconfig").is_file()
        assert (tmp_path / ".ac-guard" / "checks" / "lint.py").is_file()

    def test_uninstall_cleans_artifacts(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """D3-2: uninstall removes tracked artifacts."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".git").mkdir()
        url = _create_bare_repo(
            tmp_path / "repos",
            files={".editorconfig": "root = true\n"},
            checks={"lint.py": "# lint\n"},
        )

        _fetch(tmp_path, url)
        config = _init_config(tmp_path, rulesets=["test-rules"])
        runner.invoke(
            app, ["install", "--agent", "claude-code", "--config", str(config)]
        )

        # Uninstall
        result = runner.invoke(app, ["uninstall"])
        assert result.exit_code == 0
        assert not (installation_path(tmp_path)).is_file()
        # CLAUDE.md (rule doc) should be cleaned
        assert not (tmp_path / "CLAUDE.md").is_file()


# ---------------------------------------------------------------------------
# D4: Multi-Ruleset Interaction
# ---------------------------------------------------------------------------


class TestMultiRulesetInteraction:
    """D4: Multiple rulesets merge correctly."""

    def test_both_ruleset_rules_enforced(self, tmp_path: Path) -> None:
        """D4-1: Rules from both rulesets are active in Action guard."""
        (tmp_path / ".git").mkdir()

        url_a = _create_bare_repo(
            tmp_path / "repos-a",
            name="rules-a",
            guard_yaml_content={
                "behavior": {
                    "read": {
                        "forbidden": [{"pattern": "file:*.log", "reason": "no logs"}],
                    },
                },
            },
        )
        url_b = _create_bare_repo(
            tmp_path / "repos-b",
            name="rules-b",
            guard_yaml_content={
                "behavior": {
                    "read": {
                        "forbidden": [{"pattern": "file:*.tmp", "reason": "no tmp"}],
                    },
                },
            },
        )

        _fetch(tmp_path, url_a)
        _fetch(tmp_path, url_b)

        config = _init_config(tmp_path, rulesets=["rules-a", "rules-b"])
        runner.invoke(
            app, ["install", "--agent", "claude-code", "--config", str(config)]
        )

        # Both rules should be enforced
        assert (
            evaluate("Read", {"file_path": "debug.log"}, tmp_path).decision
            == Decision.DENY
        )
        assert (
            evaluate("Read", {"file_path": "data.tmp"}, tmp_path).decision
            == Decision.DENY
        )
        # Other files should be allowed
        assert (
            evaluate("Read", {"file_path": "main.py"}, tmp_path).decision
            == Decision.ALLOW
        )

    def test_both_ruleset_files_copied(self, tmp_path: Path) -> None:
        """D4-2: files/ and checks/ from both rulesets are installed."""
        (tmp_path / ".git").mkdir()

        url_a = _create_bare_repo(
            tmp_path / "repos-a",
            name="rules-a",
            files={"a.cfg": "config-a\n"},
        )
        url_b = _create_bare_repo(
            tmp_path / "repos-b",
            name="rules-b",
            files={"b.cfg": "config-b\n"},
            checks={"check_b.py": "# check b\n"},
        )

        _fetch(tmp_path, url_a)
        _fetch(tmp_path, url_b)

        config = _init_config(tmp_path, rulesets=["rules-a", "rules-b"])
        result = runner.invoke(
            app, ["install", "--agent", "claude-code", "--config", str(config)]
        )
        assert result.exit_code == 0

        assert (tmp_path / "a.cfg").is_file()
        assert (tmp_path / "b.cfg").is_file()
        assert (tmp_path / ".ac-guard" / "checks" / "check_b.py").is_file()
