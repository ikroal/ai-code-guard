"""Tests for GiteaChannel — mock HTTP."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from ac_guard.config.models import PrReportConfig
from ac_guard.reporter.channels.base import ChannelError, NoPrContextError
from ac_guard.reporter.channels.gitea import GiteaChannel


class TestGiteaChannel:
    """GiteaChannel send() with mocked HTTP."""

    def _make_config(
        self,
        *,
        api_url: str | None = None,
        token_env: str = "GITEA_TOKEN",
    ) -> PrReportConfig:
        return PrReportConfig(
            enabled=True,
            platform="gitea",
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
        assert GiteaChannel().name == "gitea"

    def test_send_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Successful POST with env vars."""
        monkeypatch.setenv("GITEA_TOKEN", "gt_test123")
        monkeypatch.setenv("GITEA_REPOSITORY", "owner/repo")
        monkeypatch.setenv("AI_GUARD_PR_NUMBER", "42")

        with patch("urllib.request.urlopen", return_value=self._mock_urlopen()) as m:
            GiteaChannel().send("## Report", self._make_config())
            req = m.call_args[0][0]
            assert "/repos/owner/repo/issues/42/comments" in req.full_url
            assert "Report" in json.loads(req.data)["body"]

    def test_send_failure_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GITEA_TOKEN", "gt_test123")
        monkeypatch.setenv("GITEA_REPOSITORY", "owner/repo")
        monkeypatch.setenv("AI_GUARD_PR_NUMBER", "42")

        from urllib.error import HTTPError

        with (
            patch(
                "urllib.request.urlopen",
                side_effect=HTTPError("", 403, "Forbidden", None, None),  # type: ignore[arg-type]
            ),
            pytest.raises(ChannelError, match="403"),
        ):
            GiteaChannel().send("report", self._make_config())

    def test_missing_token_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("GITEA_TOKEN", raising=False)
        monkeypatch.setenv("GITEA_REPOSITORY", "owner/repo")
        monkeypatch.setenv("AI_GUARD_PR_NUMBER", "1")

        with pytest.raises(ChannelError, match="token"):
            GiteaChannel().send("report", self._make_config())

    def test_custom_api_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GITEA_TOKEN", "gt_test123")
        monkeypatch.setenv("GITEA_REPOSITORY", "owner/repo")
        monkeypatch.setenv("AI_GUARD_PR_NUMBER", "5")

        with patch("urllib.request.urlopen", return_value=self._mock_urlopen()) as m:
            GiteaChannel().send("r", self._make_config(api_url="https://git.corp.com"))
            assert m.call_args[0][0].full_url.startswith("https://git.corp.com/")

    def test_repo_from_git_remote(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Fallback: get repo from git remote when env var missing."""
        monkeypatch.setenv("GITEA_TOKEN", "gt_test123")
        monkeypatch.delenv("GITEA_REPOSITORY", raising=False)
        monkeypatch.setenv("AI_GUARD_PR_NUMBER", "1")

        with (
            patch(
                "ac_guard.reporter.channels.gitea.get_remote_repo",
                return_value="org/my-repo",
            ),
            patch("urllib.request.urlopen", return_value=self._mock_urlopen()) as m,
        ):
            GiteaChannel().send("r", self._make_config())
            assert "/repos/org/my-repo/" in m.call_args[0][0].full_url

    def test_pr_from_api_query(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Fallback: query Gitea API for PR by branch name."""
        monkeypatch.setenv("GITEA_TOKEN", "gt_test123")
        monkeypatch.setenv("GITEA_REPOSITORY", "owner/repo")
        monkeypatch.delenv("AI_GUARD_PR_NUMBER", raising=False)

        call_count = 0

        def urlopen_side_effect(req: MagicMock) -> MagicMock:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # GET /pulls?state=open → return PR list with head.label
                return self._mock_urlopen(
                    body=json.dumps(
                        [
                            {"number": 77, "head": {"label": "feat/test"}},
                        ]
                    ).encode(),
                )
            # POST comment
            return self._mock_urlopen()

        with (
            patch(
                "ac_guard.reporter.channels.gitea.get_current_branch",
                return_value="feat/test",
            ),
            patch("urllib.request.urlopen", side_effect=urlopen_side_effect) as m,
        ):
            GiteaChannel().send("r", self._make_config())
            # Second call (POST) should use PR 77
            post_req = m.call_args_list[-1][0][0]
            assert "/issues/77/comments" in post_req.full_url

    def test_missing_pr_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """All PR detection methods fail."""
        monkeypatch.setenv("GITEA_TOKEN", "gt_test123")
        monkeypatch.setenv("GITEA_REPOSITORY", "owner/repo")
        monkeypatch.delenv("AI_GUARD_PR_NUMBER", raising=False)

        with (
            patch(
                "ac_guard.reporter.channels.gitea.get_current_branch", return_value=None
            ),
            pytest.raises(ChannelError, match="PR number"),
        ):
            GiteaChannel().send("r", self._make_config())

    def test_no_pr_raises_no_pr_context_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No PR discoverable => NoPrContextError (silent-skip contract)."""
        monkeypatch.setenv("GITEA_TOKEN", "gt_test123")
        monkeypatch.setenv("GITEA_REPOSITORY", "owner/repo")
        monkeypatch.delenv("AI_GUARD_PR_NUMBER", raising=False)

        with (
            patch(
                "ac_guard.reporter.channels.gitea.get_current_branch", return_value=None
            ),
            pytest.raises(NoPrContextError, match="PR number"),
        ):
            GiteaChannel().send("r", self._make_config())

    def test_send_retries_transient_urlerror(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Transient URLError is retried by the shared HTTP layer."""
        from urllib.error import URLError

        monkeypatch.setenv("GITEA_TOKEN", "gt_test123")
        monkeypatch.setenv("GITEA_REPOSITORY", "owner/repo")
        monkeypatch.setenv("AI_GUARD_PR_NUMBER", "42")

        side_effect = [URLError("transient"), self._mock_urlopen()]
        with (
            patch("urllib.request.urlopen", side_effect=side_effect) as m,
            patch("ac_guard.reporter.channels._http.time.sleep"),
        ):
            GiteaChannel().send("## Report", self._make_config())
        assert m.call_count == 2
