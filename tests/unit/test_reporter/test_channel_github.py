"""Tests for GitHubChannel — mock HTTP."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from ai_guard.config.models import PrReportConfig
from ai_guard.reporter.channel_base import ChannelError
from ai_guard.reporter.channel_github import GitHubChannel


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

    def test_name_is_github(self) -> None:
        ch = GitHubChannel()
        assert ch.name == "github"

    def test_send_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Successful POST returns 201."""
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_test123")
        monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
        monkeypatch.setenv("GITHUB_REF", "refs/pull/42/merge")

        mock_response = MagicMock()
        mock_response.status = 201
        mock_response.read.return_value = b'{"id": 1}'
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch(
            "urllib.request.urlopen", return_value=mock_response
        ) as mock_urlopen:
            ch = GitHubChannel()
            ch.send("## Report\n- all passed", self._make_config())

            mock_urlopen.assert_called_once()
            req = mock_urlopen.call_args[0][0]
            assert "/repos/owner/repo/issues/42/comments" in req.full_url
            body = json.loads(req.data)
            assert "Report" in body["body"]

    def test_send_failure_raises_channel_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """HTTP error raises ChannelError."""
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_test123")
        monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
        monkeypatch.setenv("GITHUB_REF", "refs/pull/42/merge")

        from urllib.error import HTTPError

        with patch(
            "urllib.request.urlopen",
            side_effect=HTTPError(
                url="",
                code=403,
                msg="Forbidden",
                hdrs=None,
                fp=None,  # type: ignore[arg-type]
            ),
        ):
            ch = GitHubChannel()
            with pytest.raises(ChannelError, match="403"):
                ch.send("report", self._make_config())

    def test_missing_token_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Missing token raises ChannelError."""
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
        monkeypatch.setenv("GITHUB_REF", "refs/pull/1/merge")

        ch = GitHubChannel()
        with pytest.raises(ChannelError, match="token"):
            ch.send("report", self._make_config())

    def test_custom_api_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Custom api_url is used instead of default."""
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_test123")
        monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
        monkeypatch.setenv("GITHUB_REF", "refs/pull/5/merge")

        mock_response = MagicMock()
        mock_response.status = 201
        mock_response.read.return_value = b'{"id": 1}'
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch(
            "urllib.request.urlopen", return_value=mock_response
        ) as mock_urlopen:
            ch = GitHubChannel()
            ch.send("report", self._make_config(api_url="https://git.corp.com/api/v3"))

            req = mock_urlopen.call_args[0][0]
            assert req.full_url.startswith("https://git.corp.com/api/v3/")

    def test_pr_number_from_ai_guard_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """AI_GUARD_PR_NUMBER fallback."""
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_test123")
        monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
        monkeypatch.delenv("GITHUB_REF", raising=False)
        monkeypatch.setenv("AI_GUARD_PR_NUMBER", "99")

        mock_response = MagicMock()
        mock_response.status = 201
        mock_response.read.return_value = b'{"id": 1}'
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch(
            "urllib.request.urlopen", return_value=mock_response
        ) as mock_urlopen:
            ch = GitHubChannel()
            ch.send("report", self._make_config())

            req = mock_urlopen.call_args[0][0]
            assert "/issues/99/comments" in req.full_url

    def test_missing_pr_number_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """No PR number available raises ChannelError."""
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_test123")
        monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
        monkeypatch.delenv("GITHUB_REF", raising=False)
        monkeypatch.delenv("AI_GUARD_PR_NUMBER", raising=False)

        ch = GitHubChannel()
        with pytest.raises(ChannelError, match="PR number"):
            ch.send("report", self._make_config())

    def test_missing_repository_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Missing GITHUB_REPOSITORY raises ChannelError."""
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_test123")
        monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
        monkeypatch.setenv("GITHUB_REF", "refs/pull/1/merge")

        ch = GitHubChannel()
        with pytest.raises(ChannelError, match="GITHUB_REPOSITORY"):
            ch.send("report", self._make_config())

    def test_parse_pr_number_from_github_ref(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """refs/pull/<n>/merge format is parsed correctly."""
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_test123")
        monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
        monkeypatch.setenv("GITHUB_REF", "refs/pull/123/merge")

        mock_response = MagicMock()
        mock_response.status = 201
        mock_response.read.return_value = b'{"id": 1}'
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch(
            "urllib.request.urlopen", return_value=mock_response
        ) as mock_urlopen:
            ch = GitHubChannel()
            ch.send("report", self._make_config())

            req = mock_urlopen.call_args[0][0]
            assert "/issues/123/comments" in req.full_url

    def test_non_pr_github_ref_falls_back(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """refs/heads/main does not contain PR number → raises."""
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_test123")
        monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
        monkeypatch.setenv("GITHUB_REF", "refs/heads/main")
        monkeypatch.delenv("AI_GUARD_PR_NUMBER", raising=False)

        ch = GitHubChannel()
        with pytest.raises(ChannelError, match="PR number"):
            ch.send("report", self._make_config())
