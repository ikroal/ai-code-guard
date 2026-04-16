"""Tests for ruleset CLI command implementations."""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_guard.cli.ruleset import (
    ruleset_cache_clear_command,
    ruleset_list_command,
)


class TestRulesetListCommand:
    """Test ruleset_list_command."""

    def test_no_cached_rulesets(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        ruleset_list_command(project_root=tmp_path)
        captured = capsys.readouterr()
        assert "No cached rulesets" in captured.out

    def test_lists_cached_rulesets(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        cache = tmp_path / ".ai-guard" / "cache"
        cache.mkdir(parents=True)
        (cache / "my-rules").mkdir()

        ruleset_list_command(project_root=tmp_path)
        captured = capsys.readouterr()
        assert "my-rules" in captured.out


class TestRulesetCacheClearCommand:
    """Test ruleset_cache_clear_command."""

    def test_empty_cache(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        ruleset_cache_clear_command(project_root=tmp_path)
        captured = capsys.readouterr()
        assert "No cached rulesets" in captured.out

    def test_clears_cache(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        cache = tmp_path / ".ai-guard" / "cache"
        cache.mkdir(parents=True)
        (cache / "rules-a").mkdir()
        (cache / "rules-b").mkdir()

        ruleset_cache_clear_command(project_root=tmp_path)
        captured = capsys.readouterr()
        assert "Cleared 2" in captured.out
