"""Tests for ruleset URL parser."""

from __future__ import annotations

import pytest

from ai_guard.ruleset.exceptions import RulesetURLError
from ai_guard.ruleset.parser import parse_ruleset_url


class TestParseRulesetUrl:
    """Test parse_ruleset_url with various URL formats."""

    # --- HTTPS URLs ---

    def test_https_url_no_version(self) -> None:
        ref = parse_ruleset_url("https://github.com/company/python-rules.git")
        assert ref.url == "https://github.com/company/python-rules.git"
        assert ref.name == "python-rules"
        assert ref.version is None
        assert ref.raw == "https://github.com/company/python-rules.git"

    def test_https_url_with_tag(self) -> None:
        ref = parse_ruleset_url("https://github.com/company/python-rules.git#v1.0.0")
        assert ref.url == "https://github.com/company/python-rules.git"
        assert ref.name == "python-rules"
        assert ref.version == "v1.0.0"

    def test_https_url_with_branch(self) -> None:
        ref = parse_ruleset_url("https://github.com/company/rules.git#main")
        assert ref.version == "main"
        assert ref.name == "rules"

    def test_https_url_without_git_suffix(self) -> None:
        ref = parse_ruleset_url("https://github.com/company/python-rules")
        assert ref.url == "https://github.com/company/python-rules"
        assert ref.name == "python-rules"

    # --- SSH URLs ---

    def test_ssh_url_no_version(self) -> None:
        ref = parse_ruleset_url("git@github.com:company/python-rules.git")
        assert ref.url == "git@github.com:company/python-rules.git"
        assert ref.name == "python-rules"
        assert ref.version is None

    def test_ssh_url_with_version(self) -> None:
        ref = parse_ruleset_url("git@github.com:company/python-rules.git#v2.0")
        assert ref.url == "git@github.com:company/python-rules.git"
        assert ref.name == "python-rules"
        assert ref.version == "v2.0"

    def test_ssh_url_nested_path(self) -> None:
        ref = parse_ruleset_url("git@gitlab.com:org/group/sub/my-rules.git#v1")
        assert ref.name == "my-rules"
        assert ref.version == "v1"

    # --- Commit SHA ---

    def test_full_commit_sha(self) -> None:
        sha = "a" * 40
        ref = parse_ruleset_url(f"https://github.com/org/rules.git#{sha}")
        assert ref.version == sha

    def test_short_commit_sha(self) -> None:
        ref = parse_ruleset_url("https://github.com/org/rules.git#abc1234")
        assert ref.version == "abc1234"

    # --- file:// URLs (for testing) ---

    def test_file_url(self) -> None:
        ref = parse_ruleset_url("file:///tmp/repos/my-rules")
        assert ref.url == "file:///tmp/repos/my-rules"
        assert ref.name == "my-rules"
        assert ref.version is None

    def test_file_url_with_version(self) -> None:
        ref = parse_ruleset_url("file:///tmp/repos/my-rules.git#v1")
        assert ref.url == "file:///tmp/repos/my-rules.git"
        assert ref.name == "my-rules"
        assert ref.version == "v1"

    # --- Name extraction edge cases ---

    def test_name_strips_dot_git(self) -> None:
        ref = parse_ruleset_url("https://host/org/repo.git")
        assert ref.name == "repo"

    def test_name_preserves_hyphens(self) -> None:
        ref = parse_ruleset_url("https://host/org/my-cool-rules.git")
        assert ref.name == "my-cool-rules"

    def test_trailing_slash_ignored(self) -> None:
        ref = parse_ruleset_url("https://host/org/repo.git/")
        assert ref.name == "repo"

    # --- Raw preservation ---

    def test_raw_preserved(self) -> None:
        raw = "git@github.com:co/rules.git#v1.0"
        ref = parse_ruleset_url(raw)
        assert ref.raw == raw

    # --- Error cases ---

    def test_empty_string_raises(self) -> None:
        with pytest.raises(RulesetURLError):
            parse_ruleset_url("")

    def test_whitespace_only_raises(self) -> None:
        with pytest.raises(RulesetURLError):
            parse_ruleset_url("   ")

    def test_bare_word_raises(self) -> None:
        with pytest.raises(RulesetURLError):
            parse_ruleset_url("just-a-name")

    def test_hash_only_version_raises(self) -> None:
        """URL with '#' but empty version should raise."""
        with pytest.raises(RulesetURLError):
            parse_ruleset_url("https://github.com/org/repo.git#")
