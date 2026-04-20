"""Shared types for AI Code Guard.

This module contains types that are used across multiple modules,
avoiding circular dependency issues between adapters and generator.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "FileSpec",
    "MARKER_BEGIN",
    "MARKER_BEGIN_HASH",
    "MARKER_END",
    "MARKER_END_HASH",
    "markers_for",
    "wrap_with_managed_block",
]


# ---------------------------------------------------------------------------
# Managed Block Markers
# ---------------------------------------------------------------------------

# HTML-comment style — embedded in rule docs (.md / .mdc) where a
# Markdown parser must hide them from rendered output.
MARKER_BEGIN = "<!-- AI-GUARD:BEGIN -->"
MARKER_END = "<!-- AI-GUARD:END -->"

# Hash-comment style — embedded in YAML / TOML / shell / Python sources
# where HTML-style comments would be a syntax error.
MARKER_BEGIN_HASH = "# AI-GUARD:BEGIN"
MARKER_END_HASH = "# AI-GUARD:END"

# Extensions whose host syntax accepts hash-style comments. Everything
# else (practically, Markdown) gets the HTML-style markers.
_HASH_COMMENT_EXTS: frozenset[str] = frozenset(
    {".yaml", ".yml", ".toml", ".sh", ".py"},
)


def markers_for(path: str) -> tuple[str, str]:
    """Return the begin/end marker strings appropriate for ``path``.

    Files whose host syntax rejects HTML comments (YAML, TOML, shell,
    Python) get the hash-style markers. Everything else — in practice
    Markdown rule docs — keeps the historical HTML-style markers.

    Args:
        path: File path whose managed block is being produced.

    Returns:
        ``(begin_marker, end_marker)`` tuple.
    """
    lower = path.lower()
    for ext in _HASH_COMMENT_EXTS:
        if lower.endswith(ext):
            return MARKER_BEGIN_HASH, MARKER_END_HASH
    return MARKER_BEGIN, MARKER_END


def wrap_with_managed_block(content: str, *, path: str | None = None) -> str:
    """Wrap ``content`` with managed block markers.

    Args:
        content: The content to wrap.
        path: Optional file path — drives marker style. If omitted,
            the historical HTML-comment markers are used for backward
            compatibility with callers that don't yet know the target
            file name.

    Returns:
        Content wrapped with the appropriate AI-GUARD markers.
    """
    begin, end = markers_for(path) if path is not None else (MARKER_BEGIN, MARKER_END)
    return f"{begin}\n{content}\n{end}\n"


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
