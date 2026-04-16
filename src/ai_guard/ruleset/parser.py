"""Ruleset URL parsing for AI Guard.

Parses ruleset reference strings into structured RulesetRef objects.
Supports HTTPS, SSH, and file:// URL formats with optional version
fragments (``url#version``).
"""

from __future__ import annotations

import re

from ai_guard.ruleset.exceptions import RulesetURLError
from ai_guard.ruleset.models import RulesetRef

__all__ = ["parse_ruleset_url"]

# Patterns that indicate a valid git-cloneable URL
_URL_INDICATORS = re.compile(
    r"^(https?://|git@|ssh://|file://)"
    r"|"
    r"\.git(/|$|#)"  # contains .git suffix
    r"|"
    r"[^/]+\.[^/]+/.+/"  # host.tld/org/repo pattern
)


def parse_ruleset_url(raw: str) -> RulesetRef:
    """Parse a ruleset URL string into a :class:`RulesetRef`.

    Splits on ``#`` to extract version. Extracts the repository name
    from the URL path. Handles HTTPS, SSH (``git@host:org/repo``),
    and ``file://`` URL formats.

    Args:
        raw: Raw ruleset URL string, optionally with ``#version`` suffix.

    Returns:
        A :class:`RulesetRef` with parsed components.

    Raises:
        RulesetURLError: If the URL is empty, unparseable, or has
            an empty version fragment.
    """
    stripped = raw.strip()
    if not stripped:
        raise RulesetURLError(raw, "empty URL")

    # Split version fragment on '#'
    url: str
    version: str | None
    if "#" in stripped:
        url, fragment = stripped.rsplit("#", 1)
        if not fragment:
            raise RulesetURLError(raw, "empty version after '#'")
        version = fragment
    else:
        url = stripped
        version = None

    # Validate that it looks like a git URL
    if not _URL_INDICATORS.search(url):
        raise RulesetURLError(raw, "not a valid git URL")

    # Extract name from URL
    name = _extract_name(url)

    return RulesetRef(url=url, name=name, version=version, raw=raw)


def _extract_name(url: str) -> str:
    """Extract repository name from a git URL.

    Handles both slash-separated (HTTPS/file) and colon-separated
    (SSH) path formats. Strips ``.git`` suffix and trailing slashes.

    Args:
        url: The clean git URL (no version fragment).

    Returns:
        The repository name (e.g. ``python-rules``).
    """
    # Remove trailing slashes
    path = url.rstrip("/")

    # Strip .git suffix
    if path.endswith(".git"):
        path = path[:-4]

    # For SSH URLs like git@host:org/repo, take after last '/' or ':'
    # For HTTPS like https://host/org/repo, take after last '/'
    for sep in ("/", ":"):
        idx = path.rfind(sep)
        if idx != -1:
            return path[idx + 1 :]

    return path
