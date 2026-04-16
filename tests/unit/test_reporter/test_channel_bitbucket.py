"""Tests for BitbucketChannel — mock HTTP."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from ai_guard.config.models import PrReportConfig
from ai_guard.reporter.channel_base import ChannelError
from ai_guard.reporter.channel_bitbucket import BitbucketChannel


class TestBitbucketChannel:
    """BitbucketChannel send() with mocked HTTP."""

    def _make_config(
        self,
        *,
        api_url: str | None = None,
        token_env: str = "BITBUCKET_TOKEN",
    ) -> PrReportConfig:
        return PrReportConfig(
            enabled=True,
            platform="bitbucket",
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
        assert BitbucketChannel().name == "bitbucket"

    def test_send_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Successful POST with env vars."""
        monkeypatch.setenv("BITBUCKET_TOKEN", "bb_test123")
        monkeypatch.setenv("BITBUCKET_REPO_FULL_NAME", "workspace/repo")
        monkeypatch.setenv("BITBUCKET_PR_ID", "42")

        with patch("urllib.request.urlopen", return_value=self._mock_urlopen()) as m:
            BitbucketChannel().send("## Report", self._make_config())
            req = m.call_args[0][0]
            assert (
                "/repositories/workspace/repo/pullrequests/42/comments" in req.full_url
            )
            body = json.loads(req.data)
            assert "Report" in body["content"]["raw"]

    def test_send_failure_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("BITBUCKET_TOKEN", "bb_test123")
        monkeypatch.setenv("BITBUCKET_REPO_FULL_NAME", "workspace/repo")
        monkeypatch.setenv("BITBUCKET_PR_ID", "42")

        from urllib.error import HTTPError

        with (
            patch(
                "urllib.request.urlopen",
                side_effect=HTTPError("", 403, "Forbidden", None, None),  # type: ignore[arg-type]
            ),
            pytest.raises(ChannelError, match="403"),
        ):
            BitbucketChannel().send("report", self._make_config())

    def test_missing_token_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("BITBUCKET_TOKEN", raising=False)
        monkeypatch.setenv("BITBUCKET_REPO_FULL_NAME", "workspace/repo")
        monkeypatch.setenv("BITBUCKET_PR_ID", "1")

        with pytest.raises(ChannelError, match="token"):
            BitbucketChannel().send("report", self._make_config())

    def test_custom_api_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("BITBUCKET_TOKEN", "bb_test123")
        monkeypatch.setenv("BITBUCKET_REPO_FULL_NAME", "workspace/repo")
        monkeypatch.setenv("BITBUCKET_PR_ID", "5")

        with patch("urllib.request.urlopen", return_value=self._mock_urlopen()) as m:
            BitbucketChannel().send(
                "r", self._make_config(api_url="https://bb.corp.com")
            )
            assert m.call_args[0][0].full_url.startswith("https://bb.corp.com/")

    def test_repo_from_git_remote(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Fallback: get repo from git remote when env var missing."""
        monkeypatch.setenv("BITBUCKET_TOKEN", "bb_test123")
        monkeypatch.delenv("BITBUCKET_REPO_FULL_NAME", raising=False)
        monkeypatch.setenv("BITBUCKET_PR_ID", "1")

        with (
            patch(
                "ai_guard.reporter.channel_bitbucket.get_remote_repo",
                return_value="org/my-repo",
            ),
            patch("urllib.request.urlopen", return_value=self._mock_urlopen()) as m,
        ):
            BitbucketChannel().send("r", self._make_config())
            assert "/repositories/org/my-repo/" in m.call_args[0][0].full_url

    def test_pr_from_api_query(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Fallback: query Bitbucket API for PR by branch name."""
        monkeypatch.setenv("BITBUCKET_TOKEN", "bb_test123")
        monkeypatch.setenv("BITBUCKET_REPO_FULL_NAME", "workspace/repo")
        monkeypatch.delenv("BITBUCKET_PR_ID", raising=False)
        monkeypatch.delenv("AI_GUARD_PR_NUMBER", raising=False)

        call_count = 0

        def urlopen_side_effect(req: MagicMock) -> MagicMock:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # GET /pullrequests?state=OPEN → return PR list
                return self._mock_urlopen(
                    body=json.dumps(
                        {
                            "values": [
                                {
                                    "id": 77,
                                    "source": {"branch": {"name": "feat/test"}},
                                },
                            ],
                        }
                    ).encode(),
                )
            # POST comment
            return self._mock_urlopen()

        with (
            patch(
                "ai_guard.reporter.channel_bitbucket.get_current_branch",
                return_value="feat/test",
            ),
            patch("urllib.request.urlopen", side_effect=urlopen_side_effect) as m,
        ):
            BitbucketChannel().send("r", self._make_config())
            # Second call (POST) should use PR 77
            post_req = m.call_args_list[-1][0][0]
            assert "/pullrequests/77/comments" in post_req.full_url

    def test_missing_pr_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """All PR detection methods fail."""
        monkeypatch.setenv("BITBUCKET_TOKEN", "bb_test123")
        monkeypatch.setenv("BITBUCKET_REPO_FULL_NAME", "workspace/repo")
        monkeypatch.delenv("BITBUCKET_PR_ID", raising=False)
        monkeypatch.delenv("AI_GUARD_PR_NUMBER", raising=False)

        with (
            patch(
                "ai_guard.reporter.channel_bitbucket.get_current_branch",
                return_value=None,
            ),
            pytest.raises(ChannelError, match="PR ID"),
        ):
            BitbucketChannel().send("r", self._make_config())
