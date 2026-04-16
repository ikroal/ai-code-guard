"""Ruleset error types for AI Guard.

Defines a hierarchy of exceptions for ruleset fetch, parse, and cache
operations. All ruleset-related errors inherit from RulesetError,
allowing callers to catch broadly or handle specific failure modes.
"""

from __future__ import annotations

__all__ = [
    "RulesetError",
    "RulesetFetchError",
    "RulesetURLError",
    "RulesetValidationError",
]


class RulesetError(Exception):
    """Base exception for all ruleset operations."""


class RulesetURLError(RulesetError):
    """Raised when a ruleset URL cannot be parsed.

    Attributes:
        raw: The raw URL string that failed to parse.
    """

    def __init__(self, raw: str, detail: str = "") -> None:
        """Initialize with the URL that failed to parse.

        Args:
            raw: The raw URL string.
            detail: Additional detail about the parsing failure.
        """
        self.raw = raw
        msg = f"Cannot parse ruleset URL: {raw!r}"
        if detail:
            msg += f" ({detail})"
        super().__init__(msg)


class RulesetFetchError(RulesetError):
    """Raised when git clone or checkout fails.

    Attributes:
        url: The URL that failed.
        stderr: Git stderr output.
    """

    def __init__(self, url: str, stderr: str = "") -> None:
        """Initialize with the URL and git error output.

        Args:
            url: The git URL that failed.
            stderr: Captured stderr from the git command.
        """
        self.url = url
        self.stderr = stderr
        msg = f"Failed to fetch ruleset from {url}"
        if stderr:
            msg += f": {stderr.strip()}"
        super().__init__(msg)


class RulesetValidationError(RulesetError):
    """Raised when a cloned ruleset lacks required structure.

    Attributes:
        name: The ruleset name.
        detail: What is missing or invalid.
    """

    def __init__(self, name: str, detail: str = "") -> None:
        """Initialize with the ruleset name and validation detail.

        Args:
            name: The ruleset directory name.
            detail: Description of the validation failure.
        """
        self.name = name
        self.detail = detail
        msg = f"Invalid ruleset '{name}'"
        if detail:
            msg += f": {detail}"
        super().__init__(msg)
