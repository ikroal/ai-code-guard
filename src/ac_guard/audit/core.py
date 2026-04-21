"""Audit module internals — 4 primitives + atomic write helper.

See ``ac_guard.audit.__init__`` for the module-level contract and
derivation rationale.
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator
    from pathlib import Path

__all__ = [
    "append_record",
    "iter_records",
    "prune_by_age",
    "rewrite_records",
]

_DEFAULT_PATH = ".ac-guard/audit.jsonl"


# ---------------------------------------------------------------------------
# B1 + S1 + Q1 + Q3
# ---------------------------------------------------------------------------


def append_record(
    record: dict[str, Any],
    project_root: Path,
    path: str = _DEFAULT_PATH,
) -> None:
    """Append one record to the audit log.

    Adds ``timestamp`` field (ISO-8601 UTC) automatically before
    serializing. Creates parent directory if needed.

    **Non-blocking (Q3)**: Any ``OSError`` is printed to stderr but
    never raised, so audit failures do not affect the caller's
    primary path (e.g., enforcer's policy decision).

    Args:
        record: Business fields for the audit entry. ``timestamp``
            will be added automatically; any ``timestamp`` key in
            the input is overwritten.
        project_root: Path to project root.
        path: Relative path under ``project_root`` (default
            ``.ac-guard/audit.jsonl``).
    """
    entry = {
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        **record,
    }

    try:
        full_path = project_root / path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        with open(full_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError as e:
        print(f"Warning: Failed to write audit log: {e}", file=sys.stderr)


# ---------------------------------------------------------------------------
# B2 + Q4
# ---------------------------------------------------------------------------


def iter_records(
    project_root: Path,
    path: str = _DEFAULT_PATH,
) -> Iterator[dict[str, Any]]:
    """Yield records in file order.

    Returns an empty iterator if the file does not exist.
    Silently skips unparseable lines (malformed JSON, empty lines).
    Raises ``OSError`` for other I/O failures so callers can decide
    fault tolerance.

    Args:
        project_root: Path to project root.
        path: Relative path under ``project_root``.

    Yields:
        Each record as a ``dict[str, Any]``, in file order.

    Raises:
        OSError: For I/O failures other than file-not-found.
    """
    full_path = project_root / path
    if not full_path.is_file():
        return

    with open(full_path, encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue  # skip unparseable lines


# ---------------------------------------------------------------------------
# B3 (generic) + Q1 + Q2
# ---------------------------------------------------------------------------


def rewrite_records(
    records: Iterable[dict[str, Any]],
    project_root: Path,
    path: str = _DEFAULT_PATH,
) -> None:
    """Atomically replace the entire audit log with ``records``.

    Writes to a temp file in the same directory as the target,
    flushes+fsyncs, then ``os.replace`` for atomic replacement —
    **crash-safe** (Q2): partial writes can never leave the target
    file in a half-written state.

    An empty ``records`` iterable replaces the log with an empty
    file (effective clear).

    Args:
        records: New sequence of records to write.
        project_root: Path to project root.
        path: Relative path under ``project_root``.

    Raises:
        OSError: If any step (directory create, temp write, rename)
            fails. Caller decides fault tolerance.
    """
    full_path = project_root / path
    full_path.parent.mkdir(parents=True, exist_ok=True)

    # Write to temp in same directory to guarantee same-filesystem
    # rename (os.replace is atomic within a filesystem).
    temp_fd, temp_name = tempfile.mkstemp(
        prefix=".audit-",
        suffix=".jsonl.tmp",
        dir=str(full_path.parent),
    )
    try:
        with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
            for record in records:
                f.write(json.dumps(record) + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_name, full_path)
    except Exception:
        # Clean up the temp file if we failed before rename.
        with contextlib.suppress(OSError):
            os.unlink(temp_name)
        raise


# ---------------------------------------------------------------------------
# B3 (schema-aware) + S1→B3 binding + Q3
# ---------------------------------------------------------------------------


def prune_by_age(
    project_root: Path,
    path: str = _DEFAULT_PATH,
    max_age_days: int = 30,
) -> int:
    """Remove records whose ``timestamp`` is older than ``max_age_days`` days.

    Uses ``iter_records`` + timestamp filter + ``rewrite_records``
    internally; atomicity inherited from ``rewrite_records``.

    **Non-blocking (Q3)**: Any ``OSError`` is printed to stderr but
    never raised. Returns 0 on failure.

    Records without a parseable ``timestamp`` field are kept
    (conservative — better to retain unidentifiable data than
    delete it accidentally).

    Args:
        project_root: Path to project root.
        path: Relative path under ``project_root``.
        max_age_days: Records strictly older than this are removed.
            ``0`` is a no-op (returns 0).

    Returns:
        Number of records removed.
    """
    if max_age_days <= 0:
        return 0

    cutoff_ts = datetime.now(tz=timezone.utc).timestamp() - max_age_days * 86400

    try:
        records = list(iter_records(project_root, path))
    except OSError as e:
        print(
            f"Warning: Failed to read audit log for prune: {e}",
            file=sys.stderr,
        )
        return 0

    kept = [r for r in records if _is_recent(r, cutoff_ts)]
    removed = len(records) - len(kept)

    if removed > 0:
        try:
            rewrite_records(kept, project_root, path)
        except OSError as e:
            print(
                f"Warning: Failed to rewrite audit log for prune: {e}",
                file=sys.stderr,
            )
            return 0

    return removed


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _is_recent(record: dict[str, Any], cutoff_ts: float) -> bool:
    """Return True if record's timestamp is >= cutoff (or unparseable).

    Conservative: records with missing or unparseable ``timestamp``
    are kept (treated as recent). This is the only place in the
    module that interprets the ``timestamp`` field — if the
    timestamp schema changes, update here.
    """
    try:
        ts = datetime.fromisoformat(record["timestamp"]).timestamp()
    except (KeyError, ValueError, TypeError):
        return True  # keep unparseable / missing-timestamp records
    return ts >= cutoff_ts
