"""Cross-module intermediate data contracts + ac-guard managed-block protocol."""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = [
    "MARKER_BEGIN",
    "MARKER_BEGIN_HASH",
    "MARKER_END",
    "MARKER_END_HASH",
    "CheckResult",
    "FileSpec",
    "StageOutcome",
    "Violation",
    "markers_for",
    "wrap_with_markers",
]


# ---------------------------------------------------------------------------
# Managed-Block Protocol
# ---------------------------------------------------------------------------
# ac-guard writes regions delimited by these markers so a subsequent
# regeneration can replace the region in place without touching any
# user edits outside the markers.

# HTML-comment style — for Markdown rule docs (.md / .mdc) where a
# Markdown renderer must hide them from rendered output.
MARKER_BEGIN = "<!-- AI-GUARD:BEGIN -->"
MARKER_END = "<!-- AI-GUARD:END -->"

# Hash-comment style — for YAML / TOML / shell / Python sources where
# HTML-style comments would be a syntax error.
MARKER_BEGIN_HASH = "# AI-GUARD:BEGIN"
MARKER_END_HASH = "# AI-GUARD:END"

# File extensions whose host syntax accepts hash-style comments.
# Everything else (practically Markdown) gets the HTML-style markers.
_HASH_COMMENT_EXTS: frozenset[str] = frozenset(
    {".yaml", ".yml", ".toml", ".sh", ".py"},
)


def markers_for(path: str) -> tuple[str, str]:
    """Return (begin, end) markers appropriate for ``path``.

    Files whose host syntax rejects HTML comments (YAML / TOML / shell /
    Python) get the hash-style markers; everything else — in practice
    Markdown rule docs — keeps the HTML-comment markers.

    Args:
        path: File path whose managed block is being produced or read.

    Returns:
        ``(begin_marker, end_marker)`` tuple.
    """
    lower = path.lower()
    if any(lower.endswith(ext) for ext in _HASH_COMMENT_EXTS):
        return MARKER_BEGIN_HASH, MARKER_END_HASH
    return MARKER_BEGIN, MARKER_END


def wrap_with_markers(path: str, content: str) -> str:
    """Wrap ``content`` with ac-guard begin/end markers chosen by ``path``.

    Args:
        path: File path whose marker style (HTML-comment vs hash-comment)
            determines the wrapper.
        content: The body text to wrap.

    Returns:
        ``{begin}\\n{content}\\n{end}\\n`` with markers selected by path.
    """
    begin, end = markers_for(path)
    return f"{begin}\n{content}\n{end}\n"


@dataclass
class Violation:
    """A single code quality violation found during checking.

    Attributes:
        file: File path where the violation was found.
        line: Line number (1-based), or None if unknown.
        column: Column number (1-based), or None if unknown.
        severity: Severity level ("error", "warning", "info").
        code: Rule code or identifier (e.g., "E501").
        message: Human-readable description of the violation.
        source: Tool that reported this violation.
    """

    file: str
    line: int | None = None
    column: int | None = None
    severity: str = "error"
    code: str = ""
    message: str = ""
    source: str = ""


@dataclass
class CheckResult:
    """Result of running a single check or hook.

    Attributes:
        name: Check or hook name.
        passed: Whether the check passed.
        violations: Detailed violation list.
        duration_ms: Execution time in milliseconds.
        output: Captured stdout/stderr for diagnostics.
        skipped: Whether the check was skipped.
    """

    name: str
    passed: bool
    violations: list[Violation] = field(default_factory=list)
    duration_ms: int = 0
    output: str = ""
    skipped: bool = False


@dataclass
class StageOutcome:
    """Outcome of a single check-stage run (one pre-commit / pre-push / ...).

    Attributes:
        stage: Git hook stage label (e.g. "pre-commit", "pre-push").
        passed: Whether all checks in the stage passed.
        results: Per-check results.
        duration_ms: Total execution time in milliseconds.
    """

    stage: str
    passed: bool
    results: list[CheckResult] = field(default_factory=list)
    duration_ms: int = 0


@dataclass
class FileSpec:
    """A file to be generated and written to disk.

    Attributes:
        path: File path relative to project root.
        content: Full file content as string (markers included if applicable).
        executable: Whether the file should have executable permissions.
    """

    path: str
    content: str
    executable: bool = False

    @classmethod
    def from_body(cls, path: str, body: str) -> FileSpec:
        """Build a FileSpec whose content is ``body`` framed by ac-guard markers.

        Marker syntax (HTML-comment vs hash-comment) is inferred from ``path``.
        Use this when the caller has the body text (the portion inside the
        markers) rather than the full on-disk content.

        Analogous to ``datetime.fromisoformat(...)``: a named constructor that
        reshapes a specific input form into the target type.
        """
        return cls(path=path, content=wrap_with_markers(path, body))
