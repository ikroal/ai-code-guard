"""Tests for the shared HTTP retry/backoff layer (WP6.2 / #67)."""

from __future__ import annotations

import io
import json
from email.message import Message
from typing import Any
from unittest.mock import patch
from urllib.error import HTTPError, URLError

import pytest

from ac_guard.reporter.channels._http import RetryPolicy, get_json, post_json
from ac_guard.reporter.channels.base import ChannelError


class _FakeResponse:
    """Stand-in for the context manager returned by urlopen."""

    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return self._payload


def _ok(payload: Any) -> _FakeResponse:
    return _FakeResponse(json.dumps(payload).encode("utf-8"))


def _http_error(code: int, *, retry_after: str | None = None) -> HTTPError:
    hdrs = Message()
    if retry_after is not None:
        hdrs["Retry-After"] = retry_after
    return HTTPError(
        url="https://example/api",
        code=code,
        msg=f"error {code}",
        hdrs=hdrs,  # type: ignore[arg-type]
        fp=io.BytesIO(b""),
    )


def _headers() -> dict[str, str]:
    return {"Authorization": "Bearer x", "Accept": "application/json"}


class _SleepRecorder:
    """Captures sleep calls for assertion."""

    def __init__(self) -> None:
        self.calls: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


def _policy(sleeper: _SleepRecorder, **overrides: Any) -> RetryPolicy:
    """Build a RetryPolicy that records sleeps into ``sleeper``."""
    return RetryPolicy(sleep=sleeper, **overrides)


class TestGetJson:
    """get_json retry/backoff behaviour."""

    def test_success_without_retry(self) -> None:
        """200 on first attempt returns parsed body and does not sleep."""
        sleeper = _SleepRecorder()
        with patch("urllib.request.urlopen", return_value=_ok({"ok": True})):
            result = get_json(
                "https://example/api",
                headers=_headers(),
                api_name="GitHub",
                retry=_policy(sleeper),
            )
        assert result == {"ok": True}
        assert sleeper.calls == []

    def test_retries_on_urlerror_then_succeeds(self) -> None:
        """Transient URLError is retried; a later 200 still succeeds."""
        sleeper = _SleepRecorder()
        side_effect = [URLError("net down"), URLError("net down"), _ok([1, 2])]
        with patch("urllib.request.urlopen", side_effect=side_effect):
            result = get_json(
                "https://example/api",
                headers=_headers(),
                api_name="GitHub",
                retry=_policy(sleeper),
            )
        assert result == [1, 2]
        assert len(sleeper.calls) == 2

    def test_retries_on_500_then_succeeds(self) -> None:
        """500 is retryable; next 200 completes the request."""
        sleeper = _SleepRecorder()
        side_effect = [_http_error(500), _ok({"ok": 1})]
        with patch("urllib.request.urlopen", side_effect=side_effect):
            result = get_json(
                "https://example/api",
                headers=_headers(),
                api_name="GitLab",
                retry=_policy(sleeper),
            )
        assert result == {"ok": 1}
        assert len(sleeper.calls) == 1

    def test_404_fails_immediately(self) -> None:
        """Non-retryable 4xx raises without consuming retry budget."""
        sleeper = _SleepRecorder()
        with (
            patch("urllib.request.urlopen", side_effect=_http_error(404)),
            pytest.raises(ChannelError, match="404"),
        ):
            get_json(
                "https://example/api",
                headers=_headers(),
                api_name="Gitea",
                retry=_policy(sleeper),
            )
        assert sleeper.calls == []

    def test_401_fails_immediately(self) -> None:
        """Auth errors must not be retried."""
        sleeper = _SleepRecorder()
        with (
            patch("urllib.request.urlopen", side_effect=_http_error(401)),
            pytest.raises(ChannelError, match="401"),
        ):
            get_json(
                "https://example/api",
                headers=_headers(),
                api_name="Bitbucket",
                retry=_policy(sleeper),
            )
        assert sleeper.calls == []

    def test_respects_retry_after_header(self) -> None:
        """429 with Retry-After overrides exponential backoff."""
        sleeper = _SleepRecorder()
        side_effect = [_http_error(429, retry_after="2"), _ok({"ok": 1})]
        with patch("urllib.request.urlopen", side_effect=side_effect):
            get_json(
                "https://example/api",
                headers=_headers(),
                api_name="GitHub",
                retry=_policy(sleeper),
            )
        assert sleeper.calls == [2.0]

    def test_exponential_backoff_sequence(self) -> None:
        """Without Retry-After, sleep durations follow exponential growth."""
        sleeper = _SleepRecorder()
        side_effect = [_http_error(503), _http_error(503), _ok({"ok": 1})]
        with patch("urllib.request.urlopen", side_effect=side_effect):
            get_json(
                "https://example/api",
                headers=_headers(),
                api_name="GitHub",
                retry=_policy(sleeper, backoff_base=0.5),
            )
        assert sleeper.calls == [0.5, 1.0]

    def test_backoff_cap_applies(self) -> None:
        """Sleep is clamped to backoff_cap even when the series would exceed it."""
        sleeper = _SleepRecorder()
        side_effect = [_http_error(503), _http_error(503), _ok({"ok": 1})]
        with patch("urllib.request.urlopen", side_effect=side_effect):
            get_json(
                "https://example/api",
                headers=_headers(),
                api_name="GitHub",
                retry=_policy(sleeper, backoff_base=4.0, backoff_cap=5.0),
            )
        # attempt 1 -> 4, attempt 2 -> min(5, 8) = 5
        assert sleeper.calls == [4.0, 5.0]


class TestPostJson:
    """post_json retry/backoff behaviour."""

    def test_retries_exhausted_on_503(self) -> None:
        """Persistent 503 exhausts retries and raises with attempt count."""
        sleeper = _SleepRecorder()
        side_effect = [_http_error(503) for _ in range(3)]
        with (
            patch("urllib.request.urlopen", side_effect=side_effect),
            pytest.raises(ChannelError, match="after 3 attempts"),
        ):
            post_json(
                "https://example/api",
                headers=_headers(),
                body={"x": 1},
                api_name="GitHub",
                retry=_policy(sleeper),
            )

    def test_empty_response_body_returns_none(self) -> None:
        """Empty response body (common for POST-no-echo) yields None."""
        with patch("urllib.request.urlopen", return_value=_FakeResponse(b"")):
            result = post_json(
                "https://example/api",
                headers=_headers(),
                body={"x": 1},
                api_name="GitHub",
                retry=_policy(_SleepRecorder()),
            )
        assert result is None

    def test_post_without_body(self) -> None:
        """POST without a body is allowed and serializes no data."""
        with patch(
            "urllib.request.urlopen", return_value=_ok({"created": True})
        ) as mock_open:
            result = post_json(
                "https://example/api",
                headers=_headers(),
                api_name="GitHub",
                retry=_policy(_SleepRecorder()),
            )
        assert result == {"created": True}
        # Verify no body was serialized onto the Request.
        (sent_req,) = mock_open.call_args.args
        assert sent_req.data is None


class TestRetryPolicyDefaults:
    """Default RetryPolicy falls back to module-level time.sleep.

    Keeps ``patch('ac_guard.reporter.channels._http.time.sleep', ...)`` style hooks
    in channel tests working without per-call RetryPolicy overrides.
    """

    def test_default_policy_uses_module_time_sleep(self) -> None:
        side_effect = [_http_error(503), _ok({"ok": 1})]
        with (
            patch("urllib.request.urlopen", side_effect=side_effect),
            patch("ac_guard.reporter.channels._http.time.sleep") as mock_sleep,
        ):
            result = get_json(
                "https://example/api",
                headers=_headers(),
                api_name="GitHub",
            )
        assert result == {"ok": 1}
        assert mock_sleep.call_count == 1
