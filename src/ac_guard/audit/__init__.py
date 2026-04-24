"""Audit module — persistent runtime decision logging.

Responsibility
--------------
Record AI policy decisions persistently (JSON Lines format),
support post-hoc audit/traceability, and manage the audit log's
retention-based lifecycle.

Guarantees
----------
- **Durability (Q1)**: Records survive process exit (flushed on close).
- **Atomicity (Q2)**: Bulk rewrite uses temp + ``os.replace`` — no
  partial-state corruption on crash mid-write.
- **Availability (Q3)**: ``append_record`` and ``prune_by_age`` are
  non-blocking (``OSError`` logged to stderr, not raised) — audit
  failures never block action_guard's hot path.
- **Append-only invariant (S2)**: Old records are never modified
  in place; bulk replace via ``rewrite_records`` is the only
  mutation path.

Record shape (S1 contract)
--------------------------
Each record is a ``dict[str, Any]``. Callers supply business fields
(agent / tool / decision / ...); this module automatically adds:

- ``timestamp``: ISO-8601 UTC string (added by ``append_record``).

Non-functional scope
--------------------
- **Single-writer model**. Concurrent writers are NOT supported;
  if introduced, Q5 Isolation dimension must be added (file lock
  or WAL).
- No encryption / tamper-evidence — logs are plain JSONL.
- No remote forwarding — logs stay local to ``project_root``.

API (all operate on ``<project_root>/<path>``)
-----------------------------------------------
- ``append_record(record, project_root, path)`` → ``None``
- ``iter_records(project_root, path)`` → ``Iterator[dict]``
- ``rewrite_records(records, project_root, path)`` → ``None``
- ``prune_by_age(project_root, path, max_age_days)`` → ``int``

API was derived via the ``deriving-module-api`` methodology:
responsibility → 9-dimensional S/B/Q analysis → 4 primitives with
coverage + minimality proof.
"""

from ac_guard.audit.core import (
    append_record,
    iter_records,
    prune_by_age,
    rewrite_records,
)

__all__ = [
    "append_record",
    "iter_records",
    "prune_by_age",
    "rewrite_records",
]
