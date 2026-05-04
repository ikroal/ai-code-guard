"""Tests for ruleset CLI command implementations."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from ac_guard.cli.ruleset import (
    RulesetCacheClearRequest,
    RulesetListRequest,
    RulesetShowRequest,
    ruleset_cache_clear_command,
    ruleset_list_command,
    ruleset_show_command,
)


def _create_cached_ruleset(
    tmp_path: Path,
    name: str = "my-rules",
    *,
    version: str | None = "v1.0",
    url: str = "https://github.com/org/rules.git",
    guard_yaml: dict | None = None,
    files: list[str] | None = None,
    checks: list[str] | None = None,
) -> Path:
    """Create a mock cached ruleset directory."""
    cache = tmp_path / ".ac-guard" / "cache" / name
    cache.mkdir(parents=True, exist_ok=True)

    # Write meta
    meta = {"url": url, "version": version, "fetched_at": "2026-04-17T00:00:00+00:00"}
    (cache / ".ruleset-meta.json").write_text(json.dumps(meta), encoding="utf-8")

    # Write guard.yaml
    content = guard_yaml or {
        "behavior": {"read": {"forbidden": [{"pattern": "file:secret/**"}]}}
    }
    (cache / "guard.yaml").write_text(yaml.dump(content), encoding="utf-8")

    # Write files
    if files:
        (cache / "files").mkdir(exist_ok=True)
        for f in files:
            (cache / "files" / f).write_text(f"# {f}", encoding="utf-8")

    # Write checks
    if checks:
        (cache / "checks").mkdir(exist_ok=True)
        for c in checks:
            (cache / "checks" / c).write_text(f"# {c}", encoding="utf-8")

    return cache


class TestRulesetListCommand:
    """Test ruleset_list_command."""

    def test_no_cached_rulesets(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        ruleset_list_command(RulesetListRequest(project_root=tmp_path))
        captured = capsys.readouterr()
        assert "No cached rulesets" in captured.out

    def test_lists_cached_rulesets(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _create_cached_ruleset(tmp_path, "my-rules", version="v1.0")

        ruleset_list_command(RulesetListRequest(project_root=tmp_path))
        captured = capsys.readouterr()
        assert "my-rules" in captured.out

    def test_list_shows_version(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _create_cached_ruleset(tmp_path, "rules", version="v2.0")

        ruleset_list_command(RulesetListRequest(project_root=tmp_path))
        captured = capsys.readouterr()
        assert "v2.0" in captured.out

    def test_list_shows_default_branch_when_no_version(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _create_cached_ruleset(tmp_path, "rules", version=None)

        ruleset_list_command(RulesetListRequest(project_root=tmp_path))
        captured = capsys.readouterr()
        assert "default" in captured.out.lower()


class TestRulesetShowCommand:
    """Test ruleset_show_command."""

    def test_show_nonexistent_ruleset(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with pytest.raises(SystemExit):
            ruleset_show_command(
                RulesetShowRequest(name="nonexistent", project_root=tmp_path)
            )

    def test_show_displays_meta(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _create_cached_ruleset(
            tmp_path,
            "company-rules",
            version="v1.0",
            url="https://github.com/org/rules.git",
        )

        ruleset_show_command(
            RulesetShowRequest(name="company-rules", project_root=tmp_path)
        )
        captured = capsys.readouterr()
        assert "company-rules" in captured.out
        assert "v1.0" in captured.out
        assert "github.com" in captured.out

    def test_show_displays_behavior_rules(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        config = {
            "behavior": {
                "read": {"forbidden": [{"pattern": "file:.env*"}]},
                "execute": {"forbidden": [{"pattern": "shell:rm -rf*"}]},
            }
        }
        _create_cached_ruleset(tmp_path, "rules", guard_yaml=config)

        ruleset_show_command(RulesetShowRequest(name="rules", project_root=tmp_path))
        captured = capsys.readouterr()
        assert "file:.env*" in captured.out
        assert "shell:rm -rf*" in captured.out

    def test_show_displays_files_list(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _create_cached_ruleset(
            tmp_path,
            "rules",
            files=[".editorconfig", ".clang-format"],
        )

        ruleset_show_command(RulesetShowRequest(name="rules", project_root=tmp_path))
        captured = capsys.readouterr()
        assert ".editorconfig" in captured.out
        assert ".clang-format" in captured.out

    def test_show_displays_checks_list(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _create_cached_ruleset(
            tmp_path,
            "rules",
            checks=["encoding_check.py", "header_check.py"],
        )

        ruleset_show_command(RulesetShowRequest(name="rules", project_root=tmp_path))
        captured = capsys.readouterr()
        assert "encoding_check.py" in captured.out
        assert "header_check.py" in captured.out


class TestRulesetCacheClearCommand:
    """Test ruleset_cache_clear_command."""

    def test_empty_cache(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        ruleset_cache_clear_command(RulesetCacheClearRequest(project_root=tmp_path))
        captured = capsys.readouterr()
        assert "No cached rulesets" in captured.out

    def test_clears_cache(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        cache = tmp_path / ".ac-guard" / "cache"
        cache.mkdir(parents=True)
        (cache / "rules-a").mkdir()
        (cache / "rules-b").mkdir()

        ruleset_cache_clear_command(RulesetCacheClearRequest(project_root=tmp_path))
        captured = capsys.readouterr()
        assert "Cleared 2" in captured.out
