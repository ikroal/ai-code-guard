"""Domain layer — cross-module intermediate data contracts.

This package holds **shared, pure data types** that flow between modules
(e.g. checker → cli → reporter). It is deliberately **not** a general-purpose
``shared`` / ``common`` bucket — additions must clear these four gates:

1. **Cross-module intermediate**: the type flows between modules as a
   contract; it is produced by one module and consumed by another, rather
   than being either module's internal implementation detail.
2. **Pure data**: plain ``@dataclass`` with no behavior; no I/O; no
   dependencies outside the standard library.
3. **Multi-consumer**: at least two non-test modules consume it.
4. **Change-impact review**: any field change must list the affected
   consumers in the PR description.

If a proposed type doesn't clear all four, it belongs in its owning module
instead. This keeps ``domain`` from turning into a grab-bag over time.
"""

from ac_guard.domain.models import CheckResult, StageOutcome, Violation

__all__ = ["CheckResult", "StageOutcome", "Violation"]
