"""Tests for BitbucketChannel — mock HTTP."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from ac_guard.config.models import PrReportConfig
from ac_guard.reporter.channels.base import ChannelError, NoPrContextError
from ac_guard.reporter.channels.bitbucket import BitbucketChannel


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
        assert BitbucketChannel.name == "bitbucket"

    def test_send_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Successful POST with env vars."""
        monkeypatch.setenv("BITBUCKET_TOKEN", "bb_test123")
        monkeypatch.setenv("BITBUCKET_REPO_FULL_NAME", "workspace/repo")
        monkeypatch.setenv("BITBUCKET_PR_ID", "42")

        with patch("urllib.request.urlopen", return_value=self._mock_urlopen()) as m:
            BitbucketChannel(self._make_config()).output("## Report")
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
            BitbucketChannel(self._make_config()).output("report")

    def test_missing_token_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("BITBUCKET_TOKEN", raising=False)
        monkeypatch.setenv("BITBUCKET_REPO_FULL_NAME", "workspace/repo")
        monkeypatch.setenv("BITBUCKET_PR_ID", "1")

        with (
            patch(
                "ac_guard.reporter.channels.git_platform.subprocess.run",
                side_effect=FileNotFoundError,
            ),
            pytest.raises(ChannelError, match="token"),
        ):
            BitbucketChannel(self._make_config()).output("report")

    def test_custom_api_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("BITBUCKET_TOKEN", "bb_test123")
        monkeypatch.setenv("BITBUCKET_REPO_FULL_NAME", "workspace/repo")
        monkeypatch.setenv("BITBUCKET_PR_ID", "5")

        with patch("urllib.request.urlopen", return_value=self._mock_urlopen()) as m:
            BitbucketChannel(self._make_config(api_url="https://bb.corp.com")).output(
                "r"
            )
            assert m.call_args[0][0].full_url.startswith("https://bb.corp.com/")

    def test_repo_from_git_remote(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Fallback: get repo from git remote when env var missing."""
        monkeypatch.setenv("BITBUCKET_TOKEN", "bb_test123")
        monkeypatch.delenv("BITBUCKET_REPO_FULL_NAME", raising=False)
        monkeypatch.setenv("BITBUCKET_PR_ID", "1")

        with (
            patch(
                "ac_guard.reporter.channels.git_platform.get_remote_repo",
                return_value="org/my-repo",
            ),
            patch("urllib.request.urlopen", return_value=self._mock_urlopen()) as m,
        ):
            BitbucketChannel(self._make_config()).output("r")
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
                "ac_guard.reporter.channels.bitbucket.get_current_branch",
                return_value="feat/test",
            ),
            patch("urllib.request.urlopen", side_effect=urlopen_side_effect) as m,
        ):
            BitbucketChannel(self._make_config()).output("r")
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
                "ac_guard.reporter.channels.bitbucket.get_current_branch",
                return_value=None,
            ),
            pytest.raises(ChannelError, match="PR ID"),
        ):
            BitbucketChannel(self._make_config()).output("r")

    def test_no_pr_raises_no_pr_context_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No PR discoverable => NoPrContextError (silent-skip contract)."""
        monkeypatch.setenv("BITBUCKET_TOKEN", "bb_test123")
        monkeypatch.setenv("BITBUCKET_REPO_FULL_NAME", "workspace/repo")
        monkeypatch.delenv("BITBUCKET_PR_ID", raising=False)
        monkeypatch.delenv("AI_GUARD_PR_NUMBER", raising=False)

        with (
            patch(
                "ac_guard.reporter.channels.bitbucket.get_current_branch",
                return_value=None,
            ),
            pytest.raises(NoPrContextError, match="PR ID"),
        ):
            BitbucketChannel(self._make_config()).output("r")

    def test_send_retries_transient_urlerror(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Transient URLError is retried by the shared HTTP layer."""
        from urllib.error import URLError

        monkeypatch.setenv("BITBUCKET_TOKEN", "bb_test123")
        monkeypatch.setenv("BITBUCKET_REPO_FULL_NAME", "workspace/repo")
        monkeypatch.setenv("BITBUCKET_PR_ID", "42")

        # GET list (empty) → POST fails → POST retry succeeds
        side_effect = [
            self._mock_urlopen(body=b"[]"),  # GET list comments
            URLError("transient"),  # POST fails
            self._mock_urlopen(),  # POST retry succeeds
        ]
        with (
            patch("urllib.request.urlopen", side_effect=side_effect) as m,
            patch("ac_guard.reporter.channels._http.time.sleep"),
        ):
            BitbucketChannel(self._make_config()).output("## Report")
        assert m.call_count == 3
