"""Tests for ac_guard.audit core primitives.

Covers the 4 primitives derived via the `deriving-module-api`
methodology (S/B/Q 9-dim analysis):

- ``append_record``   (B1 + S1 + Q1 + Q3)
- ``iter_records``    (B2 + Q4)
- ``rewrite_records`` (B3 + Q1 + Q2 — atomic write)
- ``prune_by_age``    (B3 schema-aware + S1→B3 + Q3)
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from ac_guard.audit import (
    append_record,
    iter_records,
    prune_by_age,
    rewrite_records,
)

if TYPE_CHECKING:
    pass


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


def _make_record(
    decision: str = "deny",
    operation: str = "write",
    scheme: str = "file",
    target: str = ".git/config",
    reason: str | None = "Git internals",
) -> dict:
    """Create a business-field audit record (without timestamp)."""
    return {
        "agent": "claude-code",
        "tool": "Write",
        "operation": operation,
        "scheme": scheme,
        "target": target,
        "decision": decision,
        "reason": reason,
        "matched_rule": "file:.git/**" if reason else None,
        "policy_hash": "abcd1234",
    }


# ---------------------------------------------------------------------------
# B1 + S1 + Q1 + Q3
# ---------------------------------------------------------------------------


class TestAppendRecord:
    """Tests for append_record — Q3 non-blocking, S1 timestamp addition."""

    def test_creates_file(self, tmp_path: Path) -> None:
        """Creates audit log file if it doesn't exist."""
        append_record(_make_record(), tmp_path)
        assert (tmp_path / ".ac-guard" / "audit.jsonl").is_file()

    def test_appends_record(self, tmp_path: Path) -> None:
        """Appends a JSON record to audit log."""
        append_record(_make_record(), tmp_path)
        content = (tmp_path / ".ac-guard" / "audit.jsonl").read_text(encoding="utf-8")
        records = [json.loads(line) for line in content.strip().split("\n")]
        assert len(records) == 1

    def test_multiple_records(self, tmp_path: Path) -> None:
        """Multiple calls append multiple records."""
        for _ in range(3):
            append_record(_make_record(), tmp_path)
        content = (tmp_path / ".ac-guard" / "audit.jsonl").read_text(encoding="utf-8")
        records = [json.loads(line) for line in content.strip().split("\n")]
        assert len(records) == 3

    def test_record_fields(self, tmp_path: Path) -> None:
        """Audit record contains all expected business fields + timestamp."""
        append_record(_make_record(), tmp_path)
        content = (tmp_path / ".ac-guard" / "audit.jsonl").read_text(encoding="utf-8")
        record = json.loads(content.strip())
        assert record["agent"] == "claude-code"
        assert record["tool"] == "Write"
        assert record["operation"] == "write"
        assert record["scheme"] == "file"
        assert record["target"] == ".git/config"
        assert record["decision"] == "deny"
        assert record["reason"] == "Git internals"
        assert record["matched_rule"] == "file:.git/**"
        assert record["policy_hash"] == "abcd1234"
        assert "timestamp" in record

    def test_allow_decision_no_reason(self, tmp_path: Path) -> None:
        """Allow decision with no matched rule has null reason."""
        record = _make_record(decision="allow", reason=None)
        append_record(record, tmp_path)
        content = (tmp_path / ".ac-guard" / "audit.jsonl").read_text(encoding="utf-8")
        parsed = json.loads(content.strip())
        assert parsed["decision"] == "allow"
        assert parsed["reason"] is None

    def test_io_error_does_not_raise(self, tmp_path: Path) -> None:
        """Q3: OSError does not propagate — stderr warning only."""
        readonly = tmp_path / "readonly"
        readonly.mkdir()
        readonly.chmod(0o444)
        try:
            # Must not raise even though directory is read-only.
            append_record(_make_record(), readonly)
        finally:
            readonly.chmod(0o755)

    def test_custom_audit_path(self, tmp_path: Path) -> None:
        """Custom audit path is respected."""
        append_record(_make_record(), tmp_path, "custom/audit.jsonl")
        assert (tmp_path / "custom" / "audit.jsonl").is_file()


# ---------------------------------------------------------------------------
# B2 + Q4
# ---------------------------------------------------------------------------


class TestIterRecords:
    """Tests for iter_records — B2 streaming read."""

    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        """Missing audit file yields empty iterator, not exception."""
        records = list(iter_records(tmp_path))
        assert records == []

    def test_empty_file_returns_empty(self, tmp_path: Path) -> None:
        """Existing empty file yields nothing."""
        audit_path = tmp_path / ".ac-guard" / "audit.jsonl"
        audit_path.parent.mkdir(parents=True)
        audit_path.write_text("", encoding="utf-8")
        assert list(iter_records(tmp_path)) == []

    def test_single_record(self, tmp_path: Path) -> None:
        """Single-record file yields one dict."""
        append_record(_make_record(), tmp_path)
        records = list(iter_records(tmp_path))
        assert len(records) == 1
        assert records[0]["decision"] == "deny"

    def test_multiple_records_in_order(self, tmp_path: Path) -> None:
        """Records are yielded in file (insertion) order."""
        for target in ["a", "b", "c"]:
            append_record(_make_record(target=target), tmp_path)
        records = list(iter_records(tmp_path))
        assert [r["target"] for r in records] == ["a", "b", "c"]

    def test_skips_blank_lines(self, tmp_path: Path) -> None:
        """Blank/whitespace-only lines are silently skipped."""
        audit_path = tmp_path / ".ac-guard" / "audit.jsonl"
        audit_path.parent.mkdir(parents=True)
        audit_path.write_text(
            json.dumps({"a": 1}) + "\n\n   \n" + json.dumps({"b": 2}) + "\n",
            encoding="utf-8",
        )
        records = list(iter_records(tmp_path))
        assert records == [{"a": 1}, {"b": 2}]

    def test_skips_unparseable_lines(self, tmp_path: Path) -> None:
        """Malformed JSON lines are silently skipped (conservative)."""
        audit_path = tmp_path / ".ac-guard" / "audit.jsonl"
        audit_path.parent.mkdir(parents=True)
        audit_path.write_text(
            json.dumps({"ok": 1}) + "\n" + "not json\n" + json.dumps({"ok": 2}) + "\n",
            encoding="utf-8",
        )
        records = list(iter_records(tmp_path))
        assert records == [{"ok": 1}, {"ok": 2}]

    def test_is_lazy_iterator(self, tmp_path: Path) -> None:
        """iter_records returns a generator (Q4 streaming)."""
        append_record(_make_record(), tmp_path)
        result = iter_records(tmp_path)
        # Not a list
        assert not isinstance(result, list)
        # But iterable once.
        items = list(result)
        assert len(items) == 1

    def test_custom_path(self, tmp_path: Path) -> None:
        """Honors custom relative path."""
        custom = "custom/trace.jsonl"
        append_record(_make_record(), tmp_path, custom)
        records = list(iter_records(tmp_path, custom))
        assert len(records) == 1


# ---------------------------------------------------------------------------
# B3 generic + Q1 + Q2 (atomic)
# ---------------------------------------------------------------------------


class TestRewriteRecords:
    """Tests for rewrite_records — Q2 atomic full-file replacement."""

    def test_replaces_existing_content(self, tmp_path: Path) -> None:
        """Rewrite replaces the whole file with given records."""
        for _ in range(3):
            append_record(_make_record(), tmp_path)
        rewrite_records([{"only": "one"}], tmp_path)
        records = list(iter_records(tmp_path))
        assert records == [{"only": "one"}]

    def test_empty_iterable_clears_file(self, tmp_path: Path) -> None:
        """Empty input produces an empty file (effective clear)."""
        append_record(_make_record(), tmp_path)
        rewrite_records([], tmp_path)
        audit_path = tmp_path / ".ac-guard" / "audit.jsonl"
        assert audit_path.read_text(encoding="utf-8") == ""

    def test_creates_parent_directory(self, tmp_path: Path) -> None:
        """Parent directory created if missing."""
        rewrite_records([{"a": 1}], tmp_path, "nested/path/out.jsonl")
        written = (tmp_path / "nested" / "path" / "out.jsonl").read_text(
            encoding="utf-8"
        )
        assert json.loads(written.strip()) == {"a": 1}

    def test_atomicity_on_replace_failure(self, tmp_path: Path) -> None:
        """Q2: if os.replace fails, original file content is preserved.

        Mock os.replace to raise OSError after temp file is written.
        Verify original content is untouched and temp is cleaned up.
        """
        audit_path = tmp_path / ".ac-guard" / "audit.jsonl"
        audit_path.parent.mkdir(parents=True)
        original = json.dumps({"original": True}) + "\n"
        audit_path.write_text(original, encoding="utf-8")

        with (
            patch(
                "ac_guard.audit.core.os.replace",
                side_effect=OSError("disk full"),
            ),
            pytest.raises(OSError, match="disk full"),
        ):
            rewrite_records([{"new": True}], tmp_path)

        # Original untouched
        assert audit_path.read_text(encoding="utf-8") == original
        # No leftover temp files in directory
        leftover = [
            p for p in audit_path.parent.iterdir() if p.name.startswith(".audit-")
        ]
        assert leftover == []

    def test_preserves_record_order(self, tmp_path: Path) -> None:
        """Records are written in the order provided."""
        rewrite_records(
            [{"n": 1}, {"n": 2}, {"n": 3}],
            tmp_path,
        )
        assert [r["n"] for r in iter_records(tmp_path)] == [1, 2, 3]

    def test_raises_on_oserror_below(self, tmp_path: Path) -> None:
        """rewrite_records propagates OSError (caller-decides semantics)."""
        # Point at a path whose parent creation will fail (existing regular file).
        blocker = tmp_path / "blocker"
        blocker.write_text("x", encoding="utf-8")
        with pytest.raises(OSError, match=r"blocker"):
            rewrite_records([{"a": 1}], tmp_path, "blocker/out.jsonl")


# ---------------------------------------------------------------------------
# B3 schema-aware + S1→B3 + Q3
# ---------------------------------------------------------------------------


class TestPruneByAge:
    """Tests for prune_by_age — schema-aware age-based retention."""

    def test_removes_old_records(self, tmp_path: Path) -> None:
        """Records older than max_age_days are removed."""
        audit_path = tmp_path / ".ac-guard" / "audit.jsonl"
        audit_path.parent.mkdir(parents=True)

        old_ts = "2020-01-01T00:00:00+00:00"
        new_ts = datetime.now(tz=timezone.utc).isoformat()
        audit_path.write_text(
            json.dumps({"timestamp": old_ts, "decision": "deny"})
            + "\n"
            + json.dumps({"timestamp": new_ts, "decision": "allow"})
            + "\n",
            encoding="utf-8",
        )

        removed = prune_by_age(tmp_path, max_age_days=30)
        assert removed == 1

        records = list(iter_records(tmp_path))
        assert len(records) == 1
        assert records[0]["decision"] == "allow"

    def test_zero_days_is_noop(self, tmp_path: Path) -> None:
        """max_age_days=0 means keep forever (no-op)."""
        audit_path = tmp_path / ".ac-guard" / "audit.jsonl"
        audit_path.parent.mkdir(parents=True)

        old_ts = "2020-01-01T00:00:00+00:00"
        audit_path.write_text(
            json.dumps({"timestamp": old_ts, "decision": "deny"}) + "\n",
            encoding="utf-8",
        )

        removed = prune_by_age(tmp_path, max_age_days=0)
        assert removed == 0

    def test_no_file_returns_zero(self, tmp_path: Path) -> None:
        """No audit file → 0 removed."""
        removed = prune_by_age(tmp_path, max_age_days=30)
        assert removed == 0

    def test_unparseable_timestamp_kept(self, tmp_path: Path) -> None:
        """Records with missing/malformed timestamp are kept (conservative)."""
        audit_path = tmp_path / ".ac-guard" / "audit.jsonl"
        audit_path.parent.mkdir(parents=True)
        audit_path.write_text(
            json.dumps({"timestamp": "not-a-date", "decision": "deny"})
            + "\n"
            + json.dumps({"decision": "allow"})  # no timestamp at all
            + "\n",
            encoding="utf-8",
        )
        removed = prune_by_age(tmp_path, max_age_days=1)
        assert removed == 0
        assert len(list(iter_records(tmp_path))) == 2

    def test_all_recent_nothing_removed(self, tmp_path: Path) -> None:
        """If every record is within window, no rewrite happens and 0 returned."""
        for _ in range(3):
            append_record(_make_record(), tmp_path)
        removed = prune_by_age(tmp_path, max_age_days=30)
        assert removed == 0
        # All still there.
        assert len(list(iter_records(tmp_path))) == 3

    def test_all_old_all_removed(self, tmp_path: Path) -> None:
        """All records old → all removed."""
        audit_path = tmp_path / ".ac-guard" / "audit.jsonl"
        audit_path.parent.mkdir(parents=True)
        old_ts = "2020-01-01T00:00:00+00:00"
        audit_path.write_text(
            "\n".join(json.dumps({"timestamp": old_ts, "i": i}) for i in range(3))
            + "\n",
            encoding="utf-8",
        )
        removed = prune_by_age(tmp_path, max_age_days=30)
        assert removed == 3
        assert list(iter_records(tmp_path)) == []

    def test_q3_non_blocking_on_read_error(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Q3: OSError from iter_records swallowed → returns 0, stderr warning."""
        with patch(
            "ac_guard.audit.core.iter_records",
            side_effect=OSError("read failure"),
        ):
            removed = prune_by_age(tmp_path, max_age_days=30)
        assert removed == 0
        captured = capsys.readouterr()
        assert "read failure" in captured.err

    def test_q3_non_blocking_on_write_error(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Q3: OSError from rewrite_records swallowed → returns 0."""
        audit_path = tmp_path / ".ac-guard" / "audit.jsonl"
        audit_path.parent.mkdir(parents=True)
        old_ts = "2020-01-01T00:00:00+00:00"
        audit_path.write_text(
            json.dumps({"timestamp": old_ts, "decision": "deny"}) + "\n",
            encoding="utf-8",
        )

        with patch(
            "ac_guard.audit.core.rewrite_records",
            side_effect=OSError("write failure"),
        ):
            removed = prune_by_age(tmp_path, max_age_days=30)
        assert removed == 0
        captured = capsys.readouterr()
        assert "write failure" in captured.err
