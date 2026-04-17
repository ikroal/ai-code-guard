"""Ruleset data models for AI Code Guard.

Pure data containers for ruleset references and metadata.
No I/O or validation logic — those belong in parser and fetcher.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "CACHE_DIR",
    "RulesetRef",
]

CACHE_DIR = ".ac-guard/cache"
"""Relative path from project root to the ruleset cache directory."""


@dataclass
class RulesetRef:
    """A parsed ruleset reference from a URL string.

    Attributes:
        url: The clean git clone URL (without version fragment).
        name: Extracted repository name (e.g. ``python-rules``).
        version: Optional tag, branch, or commit hash.
        raw: The original reference string before parsing.
    """

    url: str
    name: str
    version: str | None
    raw: str
