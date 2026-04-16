"""Reporter audit logging module.

Appends policy decision records to ``.ai-guard/audit.jsonl``
in JSON Lines format. Non-blocking: I/O errors are logged to
stderr but never raised.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["append_audit_log", "apply_retention"]

_DEFAULT_AUDIT_PATH = ".ai-guard/audit.jsonl"


def append_audit_log(
    record_data: dict[str, Any],
    project_root: Path,
    audit_path: str = _DEFAULT_AUDIT_PATH,
) -> None:
    """Append a policy decision record to the audit log.

    Non-blocking: any I/O error is printed to stderr but never
    raised, so audit failures do not affect the policy decision.

    Args:
        record_data: Audit record dict with fields: agent, tool,
            operation, scheme, target, decision, reason,
            matched_rule, policy_hash.
        project_root: Path to project root directory.
        audit_path: Relative path to audit log file.
    """
    record = {
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        **record_data,
    }

    try:
        full_path = project_root / audit_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        with open(full_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except OSError as e:
        print(f"Warning: Failed to write audit log: {e}", file=sys.stderr)


def apply_retention(
    project_root: Path,
    audit_path: str = _DEFAULT_AUDIT_PATH,
    retention_days: int = 30,
) -> int:
    """Remove audit records older than the retention period.

    Args:
        project_root: Path to project root directory.
        audit_path: Relative path to audit log file.
        retention_days: Days to retain. 0 means keep forever.

    Returns:
        Number of records removed.
    """
    if retention_days == 0:
        return 0

    full_path = project_root / audit_path
    if not full_path.is_file():
        return 0

    cutoff = datetime.now(tz=timezone.utc).timestamp() - (retention_days * 86400)
    kept: list[str] = []
    removed = 0

    try:
        with open(full_path, encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    ts = datetime.fromisoformat(record["timestamp"])
                    if ts.timestamp() >= cutoff:
                        kept.append(line)
                    else:
                        removed += 1
                except (json.JSONDecodeError, KeyError, ValueError):
                    kept.append(line)  # Keep unparseable records

        if removed > 0:
            full_path.write_text(
                "\n".join(kept) + "\n" if kept else "", encoding="utf-8"
            )
    except OSError as e:
        print(
            f"Warning: Failed to apply audit retention: {e}",
            file=sys.stderr,
        )

    return removed
