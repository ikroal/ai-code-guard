"""Tests for reporter git info helper."""

from __future__ import annotations

from unittest.mock import patch

from ac_guard.reporter._git_info import (
    get_current_branch,
    get_remote_repo,
    parse_repo_url,
)


class TestParseRepoUrl:
    """Test parse_repo_url with various remote URL formats."""

    def test_https_url(self) -> None:
        assert parse_repo_url("https://github.com/owner/repo.git") == "owner/repo"

    def test_https_url_no_git_suffix(self) -> None:
        assert parse_repo_url("https://github.com/owner/repo") == "owner/repo"

    def test_ssh_url(self) -> None:
        assert parse_repo_url("git@github.com:owner/repo.git") == "owner/repo"

    def test_ssh_url_no_git_suffix(self) -> None:
        assert parse_repo_url("git@gitlab.com:org/project") == "org/project"

    def test_nested_group_gitlab(self) -> None:
        """GitLab nested groups — take last two segments."""
        assert parse_repo_url("git@gitlab.com:org/group/sub/repo.git") == "sub/repo"

    def test_invalid_url_returns_none(self) -> None:
        assert parse_repo_url("not-a-url") is None

    def test_empty_returns_none(self) -> None:
        assert parse_repo_url("") is None


class TestGetRemoteRepo:
    """Test get_remote_repo with mocked subprocess."""

    def test_returns_parsed_repo(self) -> None:
        with patch(
            "ac_guard.reporter._git_info._run_git",
            return_value="https://github.com/owner/repo.git",
        ):
            assert get_remote_repo() == "owner/repo"

    def test_returns_none_on_failure(self) -> None:
        with patch(
            "ac_guard.reporter._git_info._run_git",
            return_value=None,
        ):
            assert get_remote_repo() is None


class TestGetCurrentBranch:
    """Test get_current_branch with mocked subprocess."""

    def test_returns_branch_name(self) -> None:
        with patch(
            "ac_guard.reporter._git_info._run_git",
            return_value="feat/my-feature",
        ):
            assert get_current_branch() == "feat/my-feature"

    def test_returns_none_on_failure(self) -> None:
        with patch(
            "ac_guard.reporter._git_info._run_git",
            return_value=None,
        ):
            assert get_current_branch() is None

    def test_strips_whitespace(self) -> None:
        with patch(
            "ac_guard.reporter._git_info._run_git",
            return_value="  main\n",
        ):
            assert get_current_branch() == "main"
