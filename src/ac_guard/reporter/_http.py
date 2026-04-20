"""HTTP retry/backoff layer shared by all report channels.

Wraps ``urllib.request.urlopen`` with bounded retries on transient
failures (connection errors and 408/429/5xx). Business-level 4xx
errors (401, 403, 404, ...) fail fast — retrying them would only
waste attempts.

The channel modules are thin wrappers that build auth/accept headers
and delegate transport to :func:`request_json`.
"""

from __future__ import annotations

import json
import time
import urllib.request
from typing import TYPE_CHECKING
from urllib.error import HTTPError, URLError

from ac_guard.reporter.channel_base import ChannelError

if TYPE_CHECKING:
    from collections.abc import Callable

__all__ = ["request_json"]

# HTTP status codes considered transient and worth retrying.
_RETRYABLE_STATUS = frozenset({408, 429, 500, 502, 503, 504})


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


def request_json(
    url: str,
    *,
    method: str,
    headers: dict[str, str],
    body: dict | None = None,
    api_name: str,
    max_attempts: int = 3,
    backoff_base: float = 0.5,
    backoff_cap: float = 8.0,
    sleep: Callable[[float], None] = time.sleep,
) -> dict | list | None:
    """Issue an HTTP request with bounded retries and return parsed JSON.

    Args:
        url: Absolute URL to request.
        method: HTTP method (``"GET"`` or ``"POST"``).
        headers: Fully built request headers (auth, accept, content-type).
        body: Optional JSON-serializable request body. POST without a
            body is allowed but unusual.
        api_name: Human-readable API name used in error messages
            (e.g. ``"GitHub"``).
        max_attempts: Upper bound on total attempts (>=1). Default 3.
        backoff_base: Exponential backoff base in seconds. Default 0.5.
        backoff_cap: Maximum sleep between attempts in seconds. Default 8.
        sleep: Injection point for tests.

    Returns:
        Parsed JSON body on success. Returns ``None`` when the response
        body is empty (common for POST-without-echo endpoints).

    Raises:
        ChannelError: On non-retryable HTTP errors (4xx other than 408/429)
            or when retries are exhausted on retryable failures.
    """
    data = json.dumps(body).encode("utf-8") if body is not None else None
    last_exc: BaseException | None = None

    for attempt in range(1, max_attempts + 1):
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req) as resp:  # noqa: S310 - URL is controlled by caller
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
            if attempt == max_attempts:
                break
            _wait(sleep, retry_after, attempt, backoff_base, backoff_cap)
        except URLError as exc:
            last_exc = exc
            if attempt == max_attempts:
                break
            _wait(sleep, None, attempt, backoff_base, backoff_cap)

    # Retries exhausted.
    detail = _describe(last_exc)
    raise ChannelError(
        f"{api_name} API request failed after {max_attempts} attempts: {detail}"
    ) from last_exc


def _wait(
    sleep: Callable[[float], None],
    retry_after: float | None,
    attempt: int,
    base: float,
    cap: float,
) -> None:
    """Sleep between attempts honoring ``Retry-After`` when present."""
    if retry_after is not None:
        sleep(retry_after)
        return
    delay = min(cap, base * (2 ** (attempt - 1)))
    sleep(delay)


def _describe(exc: BaseException | None) -> str:
    """Render the last exception for the retries-exhausted error message."""
    if isinstance(exc, HTTPError):
        return f"{exc.code} {exc.reason}"
    if isinstance(exc, URLError):
        return str(exc.reason)
    return repr(exc)
