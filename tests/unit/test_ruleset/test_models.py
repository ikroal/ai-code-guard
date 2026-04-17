"""Tests for ruleset data models."""

from __future__ import annotations

from ac_guard.ruleset.models import CACHE_DIR, RulesetRef


class TestRulesetRef:
    """Test RulesetRef dataclass."""

    def test_basic_construction(self) -> None:
        ref = RulesetRef(
            url="https://github.com/org/rules.git",
            name="rules",
            version="v1.0",
            raw="https://github.com/org/rules.git#v1.0",
        )
        assert ref.url == "https://github.com/org/rules.git"
        assert ref.name == "rules"
        assert ref.version == "v1.0"
        assert ref.raw == "https://github.com/org/rules.git#v1.0"

    def test_version_none(self) -> None:
        ref = RulesetRef(url="url", name="name", version=None, raw="url")
        assert ref.version is None


class TestCacheDir:
    """Test CACHE_DIR constant."""

    def test_value(self) -> None:
        assert CACHE_DIR == ".ac-guard/cache"

    def test_is_string(self) -> None:
        assert isinstance(CACHE_DIR, str)
