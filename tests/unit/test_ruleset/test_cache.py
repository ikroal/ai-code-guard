"""Tests for ruleset cache management."""

from __future__ import annotations

from pathlib import Path

from ai_guard.ruleset.cache import clear_cache, get_cache_dir, list_cached


class TestGetCacheDir:
    """Test get_cache_dir."""

    def test_creates_directory(self, tmp_path: Path) -> None:
        result = get_cache_dir(tmp_path)
        assert result == tmp_path / ".ai-guard" / "cache"
        assert result.is_dir()

    def test_idempotent(self, tmp_path: Path) -> None:
        result1 = get_cache_dir(tmp_path)
        result2 = get_cache_dir(tmp_path)
        assert result1 == result2
        assert result1.is_dir()

    def test_preserves_existing_content(self, tmp_path: Path) -> None:
        cache = tmp_path / ".ai-guard" / "cache"
        cache.mkdir(parents=True)
        (cache / "existing").mkdir()
        result = get_cache_dir(tmp_path)
        assert (result / "existing").is_dir()


class TestListCached:
    """Test list_cached."""

    def test_empty_cache(self, tmp_path: Path) -> None:
        assert list_cached(tmp_path) == []

    def test_no_cache_dir(self, tmp_path: Path) -> None:
        """No .ai-guard/cache/ directory at all."""
        assert list_cached(tmp_path) == []

    def test_lists_directories(self, tmp_path: Path) -> None:
        cache = tmp_path / ".ai-guard" / "cache"
        cache.mkdir(parents=True)
        (cache / "alpha-rules").mkdir()
        (cache / "beta-rules").mkdir()
        result = list_cached(tmp_path)
        assert result == ["alpha-rules", "beta-rules"]

    def test_ignores_files(self, tmp_path: Path) -> None:
        cache = tmp_path / ".ai-guard" / "cache"
        cache.mkdir(parents=True)
        (cache / "real-rules").mkdir()
        (cache / "stray-file.txt").write_text("oops", encoding="utf-8")
        result = list_cached(tmp_path)
        assert result == ["real-rules"]

    def test_sorted_output(self, tmp_path: Path) -> None:
        cache = tmp_path / ".ai-guard" / "cache"
        cache.mkdir(parents=True)
        (cache / "zebra").mkdir()
        (cache / "alpha").mkdir()
        (cache / "middle").mkdir()
        result = list_cached(tmp_path)
        assert result == ["alpha", "middle", "zebra"]


class TestClearCache:
    """Test clear_cache."""

    def test_clears_all(self, tmp_path: Path) -> None:
        cache = tmp_path / ".ai-guard" / "cache"
        cache.mkdir(parents=True)
        (cache / "rules-a").mkdir()
        (cache / "rules-b").mkdir()
        count = clear_cache(tmp_path)
        assert count == 2
        assert list_cached(tmp_path) == []

    def test_empty_cache_returns_zero(self, tmp_path: Path) -> None:
        cache = tmp_path / ".ai-guard" / "cache"
        cache.mkdir(parents=True)
        assert clear_cache(tmp_path) == 0

    def test_no_cache_dir_returns_zero(self, tmp_path: Path) -> None:
        assert clear_cache(tmp_path) == 0

    def test_preserves_cache_dir(self, tmp_path: Path) -> None:
        """Cache directory itself should remain after clearing."""
        cache = tmp_path / ".ai-guard" / "cache"
        cache.mkdir(parents=True)
        (cache / "rules").mkdir()
        clear_cache(tmp_path)
        assert cache.is_dir()

    def test_preserves_non_cache_ai_guard_files(self, tmp_path: Path) -> None:
        """Other files in .ai-guard/ should not be touched."""
        ai_guard = tmp_path / ".ai-guard"
        ai_guard.mkdir()
        (ai_guard / "state.json").write_text("{}", encoding="utf-8")
        cache = ai_guard / "cache"
        cache.mkdir()
        (cache / "rules").mkdir()
        clear_cache(tmp_path)
        assert (ai_guard / "state.json").is_file()
