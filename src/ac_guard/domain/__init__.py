"""Domain layer — cross-module data contracts and their domain services.

Following DDD (Eric Evans, 2003, *Domain-Driven Design*, Ch. 5), this
package holds two kinds of tactical patterns that live together in the
same bounded context:

- **Value Objects** (in ``models.py``): pure data contracts that flow
  between modules — ``FileSpec``, ``CheckResult``, ``StageOutcome``,
  ``Violation``.
- **Domain Services** (in their own sub-modules, e.g. ``managed_block``):
  stateless operations on domain concepts that are not a natural fit
  for any single Value Object.

This is deliberately **not** a general-purpose ``shared`` / ``common``
bucket. Admission is gated by explicit criteria to keep the package
from drifting into a grab-bag.

Admission criteria for **Value Objects** (``models.py``):

1. **Cross-module intermediate**: the type flows between modules as a
   contract; it is produced by one module and consumed by another,
   rather than being either module's internal implementation detail.
2. **Pure data**: ``@dataclass`` with stdlib-only construction; no I/O,
   no external dependencies, no transformational behaviour, no mutation
   methods. Construction classmethods that merely reshape inputs into
   the same type (e.g. ``datetime.fromisoformat``) are permitted.
3. **Multi-consumer**: at least two non-test modules consume it.
4. **Change-impact review**: any field change must list the affected
   consumers in the PR description.

Admission criteria for **Domain Services** (own sub-module, e.g.
``managed_block.py``):

1. **Stateless operations on domain concepts** that don't fit naturally
   on a single Value Object.
2. **stdlib-only**: no I/O, no external dependencies; operate on
   strings / VOs only.
3. **Multi-consumer** across modules.
4. **Closed-loop API**: operations form a MECE lifecycle for the
   concept; no hidden primitive leaks that force callers to compose
   at a lower level.
"""

from ac_guard.domain import managed_block
from ac_guard.domain.models import CheckResult, FileSpec, StageOutcome, Violation

__all__ = [
    "CheckResult",
    "FileSpec",
    "StageOutcome",
    "Violation",
    "managed_block",
]
