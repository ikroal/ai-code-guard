"""Domain layer — cross-module intermediate data contracts.

This package holds **shared, pure data types** that flow between modules
(e.g. checker → cli → reporter, adapters → generator). It is deliberately
**not** a general-purpose ``shared`` / ``common`` bucket — additions must
clear these four gates:

1. **Cross-module intermediate**: the type flows between modules as a
   contract; it is produced by one module and consumed by another, rather
   than being either module's internal implementation detail.
2. **Pure data plus stdlib-only factories and helpers.** ``@dataclass``
   fields, ``__repr__`` / ``__eq__`` / ``__hash__`` (via ``@dataclass``),
   **classmethod factories returning an instance of the same type**
   (e.g. ``FileSpec.from_body(...)``, analogous to
   ``datetime.fromisoformat(...)``), and **module-level pure helpers that
   operate on this module's constants/types** (e.g. ``markers_for(...)``,
   ``wrap_with_markers(...)``) are permitted. All such functions must use
   only the standard library. Forbidden: I/O, external dependencies,
   transformational/workflow logic coupling to other layers, mutation
   methods, and instance methods that do work beyond plain accessors.
3. **Multi-consumer**: at least two non-test modules consume it.
4. **Change-impact review**: any field change must list the affected
   consumers in the PR description.

If a proposed type doesn't clear all four, it belongs in its owning module
instead. This keeps ``domain`` from turning into a grab-bag over time.
"""

from ac_guard.domain.models import (
    MARKER_BEGIN,
    MARKER_BEGIN_HASH,
    MARKER_END,
    MARKER_END_HASH,
    CheckResult,
    FileSpec,
    StageOutcome,
    Violation,
    markers_for,
    wrap_with_markers,
)

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
