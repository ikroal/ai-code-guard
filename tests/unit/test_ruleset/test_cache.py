"""Tests for ruleset cache management."""

from __future__ import annotations

import json
from pathlib import Path

from ac_guard.ruleset.cache import clear_cache, get_cache_dir, list_cached, read_meta


class TestGetCacheDir:
    """Test get_cache_dir."""

    def test_creates_directory(self, tmp_path: Path) -> None:
        result = get_cache_dir(tmp_path)
        assert result == tmp_path / ".ac-guard" / "cache"
        assert result.is_dir()

    def test_idempotent(self, tmp_path: Path) -> None:
        result1 = get_cache_dir(tmp_path)
        result2 = get_cache_dir(tmp_path)
        assert result1 == result2
        assert result1.is_dir()

    def test_preserves_existing_content(self, tmp_path: Path) -> None:
        cache = tmp_path / ".ac-guard" / "cache"
        cache.mkdir(parents=True)
        (cache / "existing").mkdir()
        result = get_cache_dir(tmp_path)
        assert (result / "existing").is_dir()


class TestListCached:
    """Test list_cached."""

    def test_empty_cache(self, tmp_path: Path) -> None:
        assert list_cached(tmp_path) == []

    def test_no_cache_dir(self, tmp_path: Path) -> None:
        """No .ac-guard/cache/ directory at all."""
        assert list_cached(tmp_path) == []

    def test_lists_directories(self, tmp_path: Path) -> None:
        cache = tmp_path / ".ac-guard" / "cache"
        cache.mkdir(parents=True)
        (cache / "alpha-rules").mkdir()
        (cache / "beta-rules").mkdir()
        result = list_cached(tmp_path)
        assert result == ["alpha-rules", "beta-rules"]

    def test_ignores_files(self, tmp_path: Path) -> None:
        cache = tmp_path / ".ac-guard" / "cache"
        cache.mkdir(parents=True)
        (cache / "real-rules").mkdir()
        (cache / "stray-file.txt").write_text("oops", encoding="utf-8")
        result = list_cached(tmp_path)
        assert result == ["real-rules"]

    def test_sorted_output(self, tmp_path: Path) -> None:
        cache = tmp_path / ".ac-guard" / "cache"
        cache.mkdir(parents=True)
        (cache / "zebra").mkdir()
        (cache / "alpha").mkdir()
        (cache / "middle").mkdir()
        result = list_cached(tmp_path)
        assert result == ["alpha", "middle", "zebra"]


class TestClearCache:
    """Test clear_cache."""

    def test_clears_all(self, tmp_path: Path) -> None:
        cache = tmp_path / ".ac-guard" / "cache"
        cache.mkdir(parents=True)
        (cache / "rules-a").mkdir()
        (cache / "rules-b").mkdir()
        count = clear_cache(tmp_path)
        assert count == 2
        assert list_cached(tmp_path) == []

    def test_empty_cache_returns_zero(self, tmp_path: Path) -> None:
        cache = tmp_path / ".ac-guard" / "cache"
        cache.mkdir(parents=True)
        assert clear_cache(tmp_path) == 0

    def test_no_cache_dir_returns_zero(self, tmp_path: Path) -> None:
        assert clear_cache(tmp_path) == 0

    def test_clears_dirs_with_readonly_files(self, tmp_path: Path) -> None:
        """Regression: clear must handle read-only files (Windows .git packs)."""
        import stat

        cache = tmp_path / ".ac-guard" / "cache"
        ruleset = cache / "rules"
        ruleset.mkdir(parents=True)
        readonly_file = ruleset / "readonly.pack"
        readonly_file.write_text("data", encoding="utf-8")
        readonly_file.chmod(stat.S_IREAD)

        count = clear_cache(tmp_path)
        assert count == 1
        assert list_cached(tmp_path) == []

    def test_preserves_cache_dir(self, tmp_path: Path) -> None:
        """Cache directory itself should remain after clearing."""
        cache = tmp_path / ".ac-guard" / "cache"
        cache.mkdir(parents=True)
        (cache / "rules").mkdir()
        clear_cache(tmp_path)
        assert cache.is_dir()

    def test_preserves_non_cache_ac_guard_files(self, tmp_path: Path) -> None:
        """Other files in .ac-guard/ should not be touched."""
        ac_guard = tmp_path / ".ac-guard"
        ac_guard.mkdir()
        (ac_guard / "state.json").write_text("{}", encoding="utf-8")
        cache = ac_guard / "cache"
        cache.mkdir()
        (cache / "rules").mkdir()
        clear_cache(tmp_path)
        assert (ac_guard / "state.json").is_file()


class TestReadMeta:
    """Test read_meta."""

    def test_reads_meta_json(self, tmp_path: Path) -> None:
        cache = tmp_path / ".ac-guard" / "cache" / "my-rules"
        cache.mkdir(parents=True)
        meta = {
            "url": "https://example.com/repo.git",
            "version": "v1.0",
            "fetched_at": "2026-04-17T00:00:00",
        }
        (cache / ".ruleset-meta.json").write_text(json.dumps(meta), encoding="utf-8")

        result = read_meta(tmp_path, "my-rules")
        assert result is not None
        assert result["url"] == "https://example.com/repo.git"
        assert result["version"] == "v1.0"

    def test_returns_none_when_no_meta(self, tmp_path: Path) -> None:
        cache = tmp_path / ".ac-guard" / "cache" / "my-rules"
        cache.mkdir(parents=True)
        assert read_meta(tmp_path, "my-rules") is None

    def test_returns_none_when_no_ruleset(self, tmp_path: Path) -> None:
        assert read_meta(tmp_path, "nonexistent") is None
