"""Domain Service for the ac-guard managed-block protocol.

ac-guard writes content into files that may also contain user-written
content. To allow idempotent regeneration without disturbing user edits,
every ac-guard-owned region in a file is delimited by BEGIN/END markers:
the region is ac-guard's, the rest is the user's.

This module owns the complete CRUD lifecycle of a managed block:

    wrap(body, *, path)                         # CREATE (string level)
    has(content, *, path)                       # READ (presence)
    read(content, *, path)                      # READ (body value)
    replace(content, new_body, *, path)         # UPDATE (or append if absent)
    remove(content, *, path)                    # DELETE (preserve content around region)
    file_spec(path, body)                       # FACTORY (CREATE + FileSpec wrap)

Marker syntax is inferred from the path extension (HTML comment for
Markdown / ``.mdc``; ``#`` comment for YAML / TOML / shell / Python).
Marker constants and the dispatcher are private implementation details;
callers depend only on the six operations above.
"""

from __future__ import annotations

from ac_guard.domain.models import FileSpec

__all__ = [
    "file_spec",
    "has",
    "read",
    "remove",
    "replace",
    "wrap",
]


# ---------------------------------------------------------------------------
# Private protocol constants
# ---------------------------------------------------------------------------

# HTML-comment style — for Markdown rule docs (.md / .mdc) where a
# Markdown renderer must hide markers from rendered output.
_MARKER_BEGIN = "<!-- AI-GUARD:BEGIN -->"
_MARKER_END = "<!-- AI-GUARD:END -->"

# Hash-comment style — for YAML / TOML / shell / Python sources where
# HTML-style comments would be a syntax error.
_MARKER_BEGIN_HASH = "# AI-GUARD:BEGIN"
_MARKER_END_HASH = "# AI-GUARD:END"

# File extensions whose host syntax accepts hash-style comments.
# Everything else (practically Markdown) gets the HTML-style markers.
_HASH_COMMENT_EXTS: frozenset[str] = frozenset(
    {".yaml", ".yml", ".toml", ".sh", ".py"},
)


def _markers_for(path: str) -> tuple[str, str]:
    """Return the (begin, end) markers appropriate for ``path``."""
    lower = path.lower()
    if any(lower.endswith(ext) for ext in _HASH_COMMENT_EXTS):
        return _MARKER_BEGIN_HASH, _MARKER_END_HASH
    return _MARKER_BEGIN, _MARKER_END


# ---------------------------------------------------------------------------
# Public operations: the CRUD closed loop on a managed block
# ---------------------------------------------------------------------------


def wrap(body: str, *, path: str) -> str:
    """Produce content consisting of ``body`` wrapped in managed-block markers.

    This is the **CREATE** operation at the string level. For the common
    case of building a ``FileSpec``, prefer :func:`file_spec`.
    """
    begin, end = _markers_for(path)
    return f"{begin}\n{body}\n{end}\n"


def has(content: str, *, path: str) -> bool:
    """Whether ``content`` contains an ac-guard managed block for ``path``.

    This is the **READ (presence)** operation. Marker style is inferred
    from ``path``'s extension, so a ``.md`` file with ``#``-style markers
    (which would be a malformed managed block) returns False.
    """
    begin, end = _markers_for(path)
    return begin in content and end in content


def read(content: str, *, path: str) -> str | None:
    """Return the body inside the managed block in ``content``, or None if absent.

    This is the **READ (body)** operation. Returns ``None`` when markers
    are missing, out of order, or otherwise malformed.
    """
    begin, end = _markers_for(path)
    begin_idx = content.find(begin)
    end_idx = content.find(end)
    if begin_idx == -1 or end_idx == -1 or begin_idx + len(begin) > end_idx:
        return None
    return content[begin_idx + len(begin) : end_idx].strip("\n")


def replace(content: str, new_body: str, *, path: str) -> str:
    """Replace the managed-block body in ``content``, or append a new block if absent.

    This is the **UPDATE** operation. If the markers are present in
    ``content``, the body between them is replaced with ``new_body``;
    otherwise a new block (wrapping ``new_body``) is appended. Content
    outside the block (user territory) is always preserved.
    """
    begin, end = _markers_for(path)
    begin_idx = content.find(begin)
    end_idx = content.find(end)

    if begin_idx == -1 or end_idx == -1 or begin_idx > end_idx:
        wrapped = f"{begin}\n{new_body}\n{end}\n"
        if content.strip():
            if not content.endswith("\n"):
                content += "\n"
            return content + wrapped
        return wrapped

    before = content[:begin_idx]
    after = content[end_idx + len(end) :]
    if before and not before.endswith("\n"):
        before += "\n"
    if after and not after.startswith("\n"):
        after = "\n" + after
    return f"{before}{begin}\n{new_body}\n{end}{after}"


def remove(content: str, *, path: str) -> str:
    """Remove the managed block from ``content``, preserving surrounding content.

    This is the **DELETE** operation. Returns ``content`` unchanged if no
    managed block is present. When removing a block, adjacent blank lines
    on either side are trimmed so the result doesn't accumulate empty
    paragraphs across repeated remove/install cycles.
    """
    begin, end = _markers_for(path)
    begin_idx = content.find(begin)
    end_idx = content.find(end)
    if begin_idx == -1 or end_idx == -1 or begin_idx > end_idx:
        return content
    before = content[:begin_idx].rstrip("\n")
    after = content[end_idx + len(end) :].lstrip("\n")
    if before and after:
        return f"{before}\n{after}"
    return before or after


def file_spec(path: str, body: str) -> FileSpec:
    """Build a FileSpec whose content is ``body`` wrapped in managed-block markers.

    Convenience factory covering the common producer case (adapters and
    generator primitives that emit a new file from a rendered body).
    """
    return FileSpec(path=path, content=wrap(body, path=path))
