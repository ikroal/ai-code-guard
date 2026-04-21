"""HTTP retry/backoff layer shared by all report channels.

Wraps ``urllib.request.urlopen`` with bounded retries on transient
failures (connection errors and 408/429/5xx). Business-level 4xx
errors (401, 403, 404, ...) fail fast — retrying them would only
waste attempts.

The channel modules are thin wrappers that build auth/accept headers
and delegate transport to :func:`get_json` / :func:`post_json`.
"""

from __future__ import annotations

import json
import time
import urllib.request
from dataclasses import dataclass
from typing import TYPE_CHECKING
from urllib.error import HTTPError, URLError

from ac_guard.reporter.channel_base import ChannelError

if TYPE_CHECKING:
    from collections.abc import Callable

__all__ = ["RetryPolicy", "get_json", "post_json"]

# HTTP status codes considered transient and worth retrying.
_RETRYABLE_STATUS = frozenset({408, 429, 500, 502, 503, 504})


@dataclass(frozen=True)
class RetryPolicy:
    """Retry + exponential-backoff configuration for JSON HTTP requests.

    Attributes:
        max_attempts: Upper bound on total attempts (>=1).
        backoff_base: Exponential backoff base in seconds.
        backoff_cap: Maximum sleep between attempts in seconds.
        sleep: Sleep function to use between attempts. ``None`` means
            fall back to :func:`time.sleep` via module attribute lookup,
            which keeps existing ``patch("...time.sleep")`` test hooks
            working without per-test ``RetryPolicy`` construction.
    """

    max_attempts: int = 3
    backoff_base: float = 0.5
    backoff_cap: float = 8.0
    sleep: Callable[[float], None] | None = None


_DEFAULT_RETRY = RetryPolicy()


def get_json(
    url: str,
    *,
    headers: dict[str, str],
    api_name: str,
    retry: RetryPolicy = _DEFAULT_RETRY,
) -> dict | list | None:
    """Issue a GET request with bounded retries and return parsed JSON.

    Args:
        url: Absolute URL to request.
        headers: Fully built request headers (auth, accept).
        api_name: Human-readable API name used in error messages
            (e.g. ``"GitHub"``).
        retry: Retry/backoff policy.

    Returns:
        Parsed JSON body on success. Returns ``None`` when the response
        body is empty.

    Raises:
        ChannelError: On non-retryable HTTP errors (4xx other than
            408/429) or when retries are exhausted on retryable failures.
    """
    return _do_request(
        _PreparedRequest(url=url, method="GET", headers=headers, body=None),
        api_name=api_name,
        retry=retry,
    )


def post_json(
    url: str,
    *,
    headers: dict[str, str],
    body: dict | None = None,
    api_name: str,
    retry: RetryPolicy = _DEFAULT_RETRY,
) -> dict | list | None:
    """Issue a POST request with bounded retries and return parsed JSON.

    Args:
        url: Absolute URL to request.
        headers: Fully built request headers (auth, accept, content-type).
        body: Optional JSON-serializable request body. POST without a
            body is allowed but unusual.
        api_name: Human-readable API name used in error messages.
        retry: Retry/backoff policy.

    Returns:
        Parsed JSON body on success. Returns ``None`` when the response
        body is empty (common for POST-without-echo endpoints).

    Raises:
        ChannelError: On non-retryable HTTP errors (4xx other than
            408/429) or when retries are exhausted on retryable failures.
    """
    return _do_request(
        _PreparedRequest(url=url, method="POST", headers=headers, body=body),
        api_name=api_name,
        retry=retry,
    )


@dataclass(frozen=True)
class _PreparedRequest:
    """Immutable bundle describing a single outbound HTTP request."""

    url: str
    method: str
    headers: dict[str, str]
    body: dict | None


def _do_request(
    request: _PreparedRequest,
    *,
    api_name: str,
    retry: RetryPolicy,
) -> dict | list | None:
    """Execute the retry loop for a prepared request."""
    data = (
        json.dumps(request.body).encode("utf-8") if request.body is not None else None
    )
    last_exc: BaseException | None = None

    for attempt in range(1, retry.max_attempts + 1):
        req = urllib.request.Request(
            request.url,
            data=data,
            method=request.method,
            headers=request.headers,
        )
        try:
            with urllib.request.urlopen(req) as resp:
                raw = resp.read()
                if not raw:
                    return None
                return json.loads(raw)
        except HTTPError as exc:
            last_exc = exc
            if exc.code not in _RETRYABLE_STATUS:
                raise ChannelError(
                    f"{api_name} API returned {exc.code}: {exc.reason}"
                ) from exc
            retry_after = _parse_retry_after(
                exc.headers.get("Retry-After") if exc.headers else None
            )
            if attempt == retry.max_attempts:
                break
            _wait(retry, retry_after, attempt)
        except URLError as exc:
            last_exc = exc
            if attempt == retry.max_attempts:
                break
            _wait(retry, None, attempt)

    # Retries exhausted.
    detail = _describe(last_exc)
    raise ChannelError(
        f"{api_name} API request failed after {retry.max_attempts} attempts: {detail}"
    ) from last_exc


def _parse_retry_after(value: str | None) -> float | None:
    """Return ``Retry-After`` header value in seconds, if it parses as int.

    HTTP also permits HTTP-date format; we treat those as unparseable
    and fall back to exponential backoff. Integer-seconds form is what
    the APIs we target (GitHub/GitLab/Gitea/Bitbucket) actually emit.
    """
    if not value:
        return None
    try:
        return float(value.strip())
    except ValueError:
        return None


def _wait(retry: RetryPolicy, retry_after: float | None, attempt: int) -> None:
    """Sleep between attempts honoring ``Retry-After`` when present.

    Resolves the sleep function at call time so test patches on
    ``ac_guard.reporter._http.time.sleep`` remain effective even when
    the default :class:`RetryPolicy` is reused across calls.
    """
    sleep_fn = retry.sleep if retry.sleep is not None else time.sleep
    if retry_after is not None:
        sleep_fn(retry_after)
        return
    delay = min(retry.backoff_cap, retry.backoff_base * (2 ** (attempt - 1)))
    sleep_fn(delay)


def _describe(exc: BaseException | None) -> str:
    """Render the last exception for the retries-exhausted error message."""
    if isinstance(exc, HTTPError):
        return f"{exc.code} {exc.reason}"
    if isinstance(exc, URLError):
        return str(exc.reason)
    return repr(exc)
