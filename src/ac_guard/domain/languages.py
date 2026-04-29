"""Domain Service for the ac-guard language registry.

ac-guard recognizes a finite set of programming languages; each is
identified by a short language name (e.g. ``python``) and associated
with one or more file extensions. This module owns that mapping as a
single source of truth across the project.

Two queries are derived from the registry:

    detect_language(path)        # path → language (extension lookup, case-insensitive)
    TYPE_EXTENSIONS              # language → its extensions (as a frozenset[str])

Both are pure functions / static data — no I/O, no external dependencies.
The table is exposed publicly because consumers like code_gate's
file-type filter need the language → extensions direction with a
local fallback (treat unknown type names as literal extensions); the
fallback semantics live with that consumer rather than here.
"""

from __future__ import annotations

__all__ = [
    "TYPE_EXTENSIONS",
    "detect_language",
]


# ---------------------------------------------------------------------------
# Public registry
# ---------------------------------------------------------------------------

# Maps ac-guard language identifier → file extensions associated with
# that language. Drives both the path → language detection below and
# the bucket-aware format/lint shortcut emission in the generator
# (per-language hook IDs like ``format-python`` / ``lint-typescript``).
TYPE_EXTENSIONS: dict[str, frozenset[str]] = {
    "python": frozenset({".py", ".pyi"}),
    "javascript": frozenset({".js", ".jsx", ".mjs"}),
    "typescript": frozenset({".ts", ".tsx", ".mts"}),
    "go": frozenset({".go"}),
    "rust": frozenset({".rs"}),
    "java": frozenset({".java"}),
    "c": frozenset({".c", ".h"}),
    "cpp": frozenset({".cpp", ".cc", ".cxx", ".hpp", ".hh"}),
}


# ---------------------------------------------------------------------------
# Public operations
# ---------------------------------------------------------------------------


def detect_language(path: str) -> str | None:
    """Return the ac-guard language name for ``path``, or None if unrecognized.

    Matches by file-extension suffix against :data:`TYPE_EXTENSIONS`.
    The match is case-insensitive (so ``.PY`` resolves the same as
    ``.py``). Returns ``None`` for paths whose extension is not in
    the registry — config files, plain text, binaries, files without
    an extension, etc.
    """
    lower = path.lower()
    for lang, exts in TYPE_EXTENSIONS.items():
        if any(lower.endswith(ext) for ext in exts):
            return lang
    return None
