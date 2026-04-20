"""Tests for GitLabChannel — mock HTTP."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from ac_guard.config.models import PrReportConfig
from ac_guard.reporter.channel_base import ChannelError, NoPrContextError
from ac_guard.reporter.channel_gitlab import GitLabChannel


class TestGitLabChannel:
    """GitLabChannel send() with mocked HTTP."""

    def _make_config(
        self,
        *,
        api_url: str | None = None,
        token_env: str = "GITLAB_TOKEN",
    ) -> PrReportConfig:
        return PrReportConfig(
            enabled=True,
            platform="gitlab",
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

    def test_name(self) -> None:
        assert GitLabChannel().name == "gitlab"

    def test_send_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Successful POST with env vars."""
        monkeypatch.setenv("GITLAB_TOKEN", "glpat-test123")
        monkeypatch.setenv("CI_PROJECT_ID", "12345")
        monkeypatch.setenv("CI_MERGE_REQUEST_IID", "42")

        with patch("urllib.request.urlopen", return_value=self._mock_urlopen()) as m:
            GitLabChannel().send("## Report", self._make_config())
            req = m.call_args[0][0]
            assert "/projects/12345/merge_requests/42/notes" in req.full_url
            assert "Report" in json.loads(req.data)["body"]

    def test_send_failure_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GITLAB_TOKEN", "glpat-test123")
        monkeypatch.setenv("CI_PROJECT_ID", "12345")
        monkeypatch.setenv("CI_MERGE_REQUEST_IID", "42")

        from urllib.error import HTTPError

        with (
            patch(
                "urllib.request.urlopen",
                side_effect=HTTPError("", 403, "Forbidden", None, None),  # type: ignore[arg-type]
            ),
            pytest.raises(ChannelError, match="403"),
        ):
            GitLabChannel().send("report", self._make_config())

    def test_missing_token_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("GITLAB_TOKEN", raising=False)
        monkeypatch.setenv("CI_PROJECT_ID", "12345")
        monkeypatch.setenv("CI_MERGE_REQUEST_IID", "1")

        with pytest.raises(ChannelError, match="token"):
            GitLabChannel().send("report", self._make_config())

    def test_custom_api_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GITLAB_TOKEN", "glpat-test123")
        monkeypatch.setenv("CI_PROJECT_ID", "12345")
        monkeypatch.setenv("CI_MERGE_REQUEST_IID", "5")

        with patch("urllib.request.urlopen", return_value=self._mock_urlopen()) as m:
            GitLabChannel().send(
                "r", self._make_config(api_url="https://gitlab.corp.com")
            )
            assert m.call_args[0][0].full_url.startswith("https://gitlab.corp.com/")

    def test_repo_from_git_remote(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Fallback: get project ID from git remote when env var missing."""
        monkeypatch.setenv("GITLAB_TOKEN", "glpat-test123")
        monkeypatch.delenv("CI_PROJECT_ID", raising=False)
        monkeypatch.setenv("CI_MERGE_REQUEST_IID", "1")

        with (
            patch(
                "ac_guard.reporter.channel_gitlab.get_remote_repo",
                return_value="org/my-repo",
            ),
            patch("urllib.request.urlopen", return_value=self._mock_urlopen()) as m,
        ):
            GitLabChannel().send("r", self._make_config())
            # URL-encoded owner/repo: org%2Fmy-repo
            assert "/projects/org%2Fmy-repo/" in m.call_args[0][0].full_url

    def test_pr_from_api_query(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Fallback: query GitLab API for MR by branch name."""
        monkeypatch.setenv("GITLAB_TOKEN", "glpat-test123")
        monkeypatch.setenv("CI_PROJECT_ID", "12345")
        monkeypatch.delenv("CI_MERGE_REQUEST_IID", raising=False)
        monkeypatch.delenv("AI_GUARD_PR_NUMBER", raising=False)

        call_count = 0

        def urlopen_side_effect(req: MagicMock) -> MagicMock:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # GET /merge_requests?source_branch=... → return MR list
                return self._mock_urlopen(body=json.dumps([{"iid": 77}]).encode())
            # POST note
            return self._mock_urlopen()

        with (
            patch(
                "ac_guard.reporter.channel_gitlab.get_current_branch",
                return_value="feat/test",
            ),
            patch("urllib.request.urlopen", side_effect=urlopen_side_effect) as m,
        ):
            GitLabChannel().send("r", self._make_config())
            # Second call (POST) should use MR 77
            post_req = m.call_args_list[-1][0][0]
            assert "/merge_requests/77/notes" in post_req.full_url

    def test_missing_pr_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """All MR detection methods fail."""
        monkeypatch.setenv("GITLAB_TOKEN", "glpat-test123")
        monkeypatch.setenv("CI_PROJECT_ID", "12345")
        monkeypatch.delenv("CI_MERGE_REQUEST_IID", raising=False)
        monkeypatch.delenv("AI_GUARD_PR_NUMBER", raising=False)

        with (
            patch(
                "ac_guard.reporter.channel_gitlab.get_current_branch", return_value=None
            ),
            pytest.raises(ChannelError, match="MR IID"),
        ):
            GitLabChannel().send("r", self._make_config())

    def test_no_mr_raises_no_pr_context_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No MR discoverable => NoPrContextError (silent-skip contract)."""
        monkeypatch.setenv("GITLAB_TOKEN", "glpat-test123")
        monkeypatch.setenv("CI_PROJECT_ID", "12345")
        monkeypatch.delenv("CI_MERGE_REQUEST_IID", raising=False)
        monkeypatch.delenv("AI_GUARD_PR_NUMBER", raising=False)

        with (
            patch(
                "ac_guard.reporter.channel_gitlab.get_current_branch", return_value=None
            ),
            pytest.raises(NoPrContextError, match="MR IID"),
        ):
            GitLabChannel().send("r", self._make_config())

    def test_send_retries_transient_urlerror(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Transient URLError is retried by the shared HTTP layer."""
        from urllib.error import URLError

        monkeypatch.setenv("GITLAB_TOKEN", "glpat-test123")
        monkeypatch.setenv("CI_PROJECT_ID", "12345")
        monkeypatch.setenv("CI_MERGE_REQUEST_IID", "42")

        side_effect = [URLError("transient"), self._mock_urlopen()]
        with (
            patch("urllib.request.urlopen", side_effect=side_effect) as m,
            patch("ac_guard.reporter._http.time.sleep"),
        ):
            GitLabChannel().send("## Report", self._make_config())
        assert m.call_count == 2
