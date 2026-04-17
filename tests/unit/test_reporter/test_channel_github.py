"""Tests for GitHubChannel — mock HTTP."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from ac_guard.config.models import PrReportConfig
from ac_guard.reporter.channel_base import ChannelError
from ac_guard.reporter.channel_github import GitHubChannel


class TestGitHubChannel:
    """GitHubChannel send() with mocked HTTP."""

    def _make_config(
        self,
        *,
        api_url: str | None = None,
        token_env: str = "GITHUB_TOKEN",
    ) -> PrReportConfig:
        return PrReportConfig(
            enabled=True,
            platform="github",
            api_url=api_url,
            token_env=token_env,
        )

    @staticmethod
    def _mock_urlopen(status: int = 201, body: bytes = b'{"id": 1}') -> MagicMock:
        mock_response = MagicMock()
        mock_response.status = status
        mock_response.read.return_value = body
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        return mock_response

    def test_name_is_github(self) -> None:
        assert GitHubChannel().name == "github"

    def test_send_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Successful POST with env vars."""
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_test123")
        monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
        monkeypatch.setenv("GITHUB_REF", "refs/pull/42/merge")

        with patch("urllib.request.urlopen", return_value=self._mock_urlopen()) as m:
            GitHubChannel().send("## Report", self._make_config())
            req = m.call_args[0][0]
            assert "/repos/owner/repo/issues/42/comments" in req.full_url
            assert "Report" in json.loads(req.data)["body"]

    def test_send_failure_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_test123")
        monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
        monkeypatch.setenv("GITHUB_REF", "refs/pull/42/merge")

        from urllib.error import HTTPError

        with (
            patch(
                "urllib.request.urlopen",
                side_effect=HTTPError("", 403, "Forbidden", None, None),  # type: ignore[arg-type]
            ),
            pytest.raises(ChannelError, match="403"),
        ):
            GitHubChannel().send("report", self._make_config())

    def test_missing_token_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
        monkeypatch.setenv("GITHUB_REF", "refs/pull/1/merge")

        with pytest.raises(ChannelError, match="token"):
            GitHubChannel().send("report", self._make_config())

    def test_custom_api_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_test123")
        monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
        monkeypatch.setenv("GITHUB_REF", "refs/pull/5/merge")

        with patch("urllib.request.urlopen", return_value=self._mock_urlopen()) as m:
            GitHubChannel().send(
                "r", self._make_config(api_url="https://git.corp.com/api/v3")
            )
            assert m.call_args[0][0].full_url.startswith("https://git.corp.com/api/v3/")

    def test_pr_number_from_ac_guard_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_test123")
        monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
        monkeypatch.delenv("GITHUB_REF", raising=False)
        monkeypatch.setenv("AI_GUARD_PR_NUMBER", "99")

        with patch("urllib.request.urlopen", return_value=self._mock_urlopen()) as m:
            GitHubChannel().send("r", self._make_config())
            assert "/issues/99/comments" in m.call_args[0][0].full_url

    def test_pr_number_from_github_ref(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_test123")
        monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
        monkeypatch.setenv("GITHUB_REF", "refs/pull/123/merge")
        monkeypatch.delenv("AI_GUARD_PR_NUMBER", raising=False)

        with patch("urllib.request.urlopen", return_value=self._mock_urlopen()) as m:
            GitHubChannel().send("r", self._make_config())
            assert "/issues/123/comments" in m.call_args[0][0].full_url

    def test_pr_number_from_api_query(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Fallback: query GitHub API for PR by branch name."""
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_test123")
        monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
        monkeypatch.delenv("GITHUB_REF", raising=False)
        monkeypatch.delenv("AI_GUARD_PR_NUMBER", raising=False)

        call_count = 0

        def urlopen_side_effect(req: MagicMock) -> MagicMock:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # GET /pulls?head=... → return PR list
                return self._mock_urlopen(body=json.dumps([{"number": 77}]).encode())
            # POST comment
            return self._mock_urlopen()

        with (
            patch(
                "ac_guard.reporter.channel_github.get_current_branch",
                return_value="feat/test",
            ),
            patch("urllib.request.urlopen", side_effect=urlopen_side_effect) as m,
        ):
            GitHubChannel().send("r", self._make_config())
            # Second call (POST) should use PR 77
            post_req = m.call_args_list[-1][0][0]
            assert "/issues/77/comments" in post_req.full_url

    def test_repo_from_git_remote(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Fallback: get repo from git remote when env var missing."""
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_test123")
        monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
        monkeypatch.setenv("GITHUB_REF", "refs/pull/1/merge")

        with (
            patch(
                "ac_guard.reporter.channel_github.get_remote_repo",
                return_value="org/my-repo",
            ),
            patch("urllib.request.urlopen", return_value=self._mock_urlopen()) as m,
        ):
            GitHubChannel().send("r", self._make_config())
            assert "/repos/org/my-repo/" in m.call_args[0][0].full_url

    def test_missing_repo_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_test123")
        monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
        monkeypatch.setenv("GITHUB_REF", "refs/pull/1/merge")

        with (
            patch(
                "ac_guard.reporter.channel_github.get_remote_repo", return_value=None
            ),
            pytest.raises(ChannelError, match="repository"),
        ):
            GitHubChannel().send("r", self._make_config())

    def test_missing_pr_number_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """All PR detection methods fail."""
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_test123")
        monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
        monkeypatch.delenv("GITHUB_REF", raising=False)
        monkeypatch.delenv("AI_GUARD_PR_NUMBER", raising=False)

        with (
            patch(
                "ac_guard.reporter.channel_github.get_current_branch", return_value=None
            ),
            pytest.raises(ChannelError, match="PR number"),
        ):
            GitHubChannel().send("r", self._make_config())

    def test_non_pr_github_ref_falls_to_api(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """refs/heads/main triggers API query fallback."""
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_test123")
        monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
        monkeypatch.setenv("GITHUB_REF", "refs/heads/main")
        monkeypatch.delenv("AI_GUARD_PR_NUMBER", raising=False)

        with (
            patch(
                "ac_guard.reporter.channel_github.get_current_branch", return_value=None
            ),
            pytest.raises(ChannelError, match="PR number"),
        ):
            GitHubChannel().send("r", self._make_config())
