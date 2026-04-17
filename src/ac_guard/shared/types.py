"""Shared types for AI Code Guard.

This module contains types that are used across multiple modules,
avoiding circular dependency issues between adapters and generator.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "FileSpec",
    "MARKER_BEGIN",
    "MARKER_END",
    "wrap_with_managed_block",
]


# ---------------------------------------------------------------------------
# Managed Block Markers
# ---------------------------------------------------------------------------

MARKER_BEGIN = "<!-- AI-GUARD:BEGIN -->"
MARKER_END = "<!-- AI-GUARD:END -->"


def wrap_with_managed_block(content: str) -> str:
    """Wrap content with managed block markers.

    Args:
        content: The content to wrap.

    Returns:
        Content wrapped with AI-GUARD markers.
    """
    return f"{MARKER_BEGIN}\n{content}\n{MARKER_END}\n"


# ---------------------------------------------------------------------------
# Shared Types
# ---------------------------------------------------------------------------


@dataclass
class FileSpec:
    """A file to be generated and written to disk.

    Attributes:
        path: File path relative to project root.
        content: File content as string.
        executable: Whether the file should have executable permissions.
    """

    path: str
    content: str
    executable: bool = False
