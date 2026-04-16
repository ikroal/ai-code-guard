"""Tests for ruleset fetcher."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
import yaml

from ai_guard.ruleset.exceptions import (
    RulesetFetchError,
    RulesetValidationError,
)
from ai_guard.ruleset.fetcher import (
    _is_commit_sha,
    fetch_ruleset,
    validate_ruleset_dir,
)
from ai_guard.ruleset.models import RulesetRef

# ---------------------------------------------------------------------------
# Helpers — create local git repos for testing
# ---------------------------------------------------------------------------


def _create_bare_repo(
    base: Path,
    name: str = "test-rules",
    *,
    with_guard_yaml: bool = True,
    guard_yaml_content: dict | None = None,
    tag: str | None = None,
) -> str:
    """Create a local bare git repo and return a file:// URL.

    Args:
        base: Parent directory for the repo.
        name: Repo directory name.
        with_guard_yaml: Whether to include a guard.yaml.
        guard_yaml_content: Custom guard.yaml content dict.
        tag: Optional tag to create.

    Returns:
        file:// URL pointing to the bare repo.
    """
    work = base / f"{name}-work"
    bare = base / f"{name}.git"

    # Create a working repo, add files, push to bare
    base.mkdir(parents=True, exist_ok=True)
    work.mkdir()
    bare.mkdir()

    subprocess.run(
        ["git", "init", "--bare", str(bare)], check=True, capture_output=True
    )
    subprocess.run(
        ["git", "clone", str(bare), str(work)],
        check=True,
        capture_output=True,
    )

    # Configure git user for commits
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

    if with_guard_yaml:
        content = guard_yaml_content or {
            "behavior": {
                "read": {"forbidden": [{"pattern": "file:secret/**"}]},
            }
        }
        (work / "guard.yaml").write_text(yaml.dump(content), encoding="utf-8")

    # Create files/ and checks/ directories
    (work / "files").mkdir()
    (work / "files" / ".clang-format").write_text(
        "BasedOnStyle: LLVM\n", encoding="utf-8"
    )
    (work / "checks").mkdir()
    (work / "checks" / "my_check.py").write_text("# check\n", encoding="utf-8")

    subprocess.run(["git", "add", "."], cwd=work, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=work,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "push", "origin", "HEAD"],
        cwd=work,
        check=True,
        capture_output=True,
    )

    if tag:
        subprocess.run(
            ["git", "tag", tag],
            cwd=work,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "push", "origin", tag],
            cwd=work,
            check=True,
            capture_output=True,
        )

    return bare.as_uri()


def _get_head_sha(bare_path: str) -> str:
    """Get the HEAD commit SHA from a bare repo URL."""
    from urllib.parse import urlparse
    from urllib.request import url2pathname

    path = url2pathname(urlparse(bare_path).path)
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=path,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestIsCommitSha:
    """Test _is_commit_sha helper."""

    def test_40_hex_chars(self) -> None:
        assert _is_commit_sha("a" * 40) is True

    def test_7_hex_chars(self) -> None:
        assert _is_commit_sha("abc1234") is True

    def test_short_hex_6_chars(self) -> None:
        """6 chars is too short to be a reliable SHA."""
        assert _is_commit_sha("abc123") is False

    def test_tag_name(self) -> None:
        assert _is_commit_sha("v1.0.0") is False

    def test_branch_name(self) -> None:
        assert _is_commit_sha("main") is False

    def test_7_valid_hex(self) -> None:
        assert _is_commit_sha("abcdef0") is True  # 7 hex chars

    def test_contains_nonhex(self) -> None:
        assert _is_commit_sha("abcdxyz") is False


class TestValidateRulesetDir:
    """Test validate_ruleset_dir."""

    def test_valid_dir(self, tmp_path: Path) -> None:
        (tmp_path / "guard.yaml").write_text(
            yaml.dump({"behavior": {}}), encoding="utf-8"
        )
        # Should not raise
        validate_ruleset_dir(tmp_path)

    def test_missing_guard_yaml(self, tmp_path: Path) -> None:
        with pytest.raises(RulesetValidationError, match=r"guard\.yaml"):
            validate_ruleset_dir(tmp_path)

    def test_empty_guard_yaml(self, tmp_path: Path) -> None:
        (tmp_path / "guard.yaml").write_text("", encoding="utf-8")
        # Empty YAML is valid (parsed as None/empty) — should not raise
        validate_ruleset_dir(tmp_path)


class TestFetchRuleset:
    """Test fetch_ruleset with local bare repos."""

    def test_clone_creates_directory(self, tmp_path: Path) -> None:
        url = _create_bare_repo(tmp_path / "repos")
        cache_root = tmp_path / "cache"
        cache_root.mkdir()

        ref = RulesetRef(url=url, name="test-rules", version=None, raw=url)
        result = fetch_ruleset(ref, cache_root)

        assert result.is_dir()
        assert result.name == "test-rules"
        assert (result / "guard.yaml").is_file()
        assert (result / "files" / ".clang-format").is_file()
        assert (result / "checks" / "my_check.py").is_file()

    def test_clone_with_tag(self, tmp_path: Path) -> None:
        url = _create_bare_repo(tmp_path / "repos", tag="v1.0")
        cache_root = tmp_path / "cache"
        cache_root.mkdir()

        ref = RulesetRef(url=url, name="test-rules", version="v1.0", raw=f"{url}#v1.0")
        result = fetch_ruleset(ref, cache_root)

        assert result.is_dir()
        assert (result / "guard.yaml").is_file()

    def test_clone_with_commit_sha(self, tmp_path: Path) -> None:
        url = _create_bare_repo(tmp_path / "repos")
        sha = _get_head_sha(url)
        cache_root = tmp_path / "cache"
        cache_root.mkdir()

        ref = RulesetRef(url=url, name="test-rules", version=sha, raw=f"{url}#{sha}")
        result = fetch_ruleset(ref, cache_root)

        assert result.is_dir()
        assert (result / "guard.yaml").is_file()

    def test_re_fetch_replaces_existing(self, tmp_path: Path) -> None:
        url = _create_bare_repo(tmp_path / "repos")
        cache_root = tmp_path / "cache"
        cache_root.mkdir()

        ref = RulesetRef(url=url, name="test-rules", version=None, raw=url)

        # First fetch
        result1 = fetch_ruleset(ref, cache_root)
        assert result1.is_dir()

        # Second fetch should succeed (replace)
        result2 = fetch_ruleset(ref, cache_root)
        assert result2.is_dir()
        assert (result2 / "guard.yaml").is_file()

    def test_invalid_url_raises(self, tmp_path: Path) -> None:
        cache_root = tmp_path / "cache"
        cache_root.mkdir()

        ref = RulesetRef(
            url="file:///nonexistent/repo.git",
            name="bad",
            version=None,
            raw="file:///nonexistent/repo.git",
        )
        with pytest.raises(RulesetFetchError):
            fetch_ruleset(ref, cache_root)

    def test_missing_guard_yaml_raises(self, tmp_path: Path) -> None:
        url = _create_bare_repo(tmp_path / "repos", with_guard_yaml=False)
        cache_root = tmp_path / "cache"
        cache_root.mkdir()

        ref = RulesetRef(url=url, name="test-rules", version=None, raw=url)
        with pytest.raises(RulesetValidationError, match=r"guard\.yaml"):
            fetch_ruleset(ref, cache_root)

    def test_writes_meta_json(self, tmp_path: Path) -> None:
        url = _create_bare_repo(tmp_path / "repos", tag="v1.0")
        cache_root = tmp_path / "cache"
        cache_root.mkdir()

        ref = RulesetRef(url=url, name="test-rules", version="v1.0", raw=f"{url}#v1.0")
        result = fetch_ruleset(ref, cache_root)

        meta_path = result / ".ruleset-meta.json"
        assert meta_path.is_file()
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        assert meta["url"] == url
        assert meta["version"] == "v1.0"
        assert "fetched_at" in meta
