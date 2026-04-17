"""Tests for Reporter audit logging (WP2.3)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from ac_guard.config.models import Rule
from ac_guard.enforcer.matcher import Decision, PolicyDecision
from ac_guard.reporter.audit import append_audit_log, apply_retention


def _make_record(
    decision: str = "deny",
    operation: str = "write",
    scheme: str = "file",
    target: str = ".git/config",
    reason: str | None = "Git internals",
) -> dict:
    """Create an audit record dict for testing."""
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


class TestAppendAuditLog:
    """Tests for append_audit_log function."""

    def test_creates_file(self, tmp_path: Path) -> None:
        """Creates audit log file if it doesn't exist."""
        append_audit_log(_make_record(), tmp_path)
        assert (tmp_path / ".ac-guard" / "audit.jsonl").is_file()

    def test_appends_record(self, tmp_path: Path) -> None:
        """Appends a JSON record to audit log."""
        append_audit_log(_make_record(), tmp_path)
        content = (tmp_path / ".ac-guard" / "audit.jsonl").read_text()
        records = [json.loads(line) for line in content.strip().split("\n")]
        assert len(records) == 1

    def test_multiple_records(self, tmp_path: Path) -> None:
        """Multiple calls append multiple records."""
        for _ in range(3):
            append_audit_log(_make_record(), tmp_path)
        content = (tmp_path / ".ac-guard" / "audit.jsonl").read_text()
        records = [json.loads(line) for line in content.strip().split("\n")]
        assert len(records) == 3

    def test_record_fields(self, tmp_path: Path) -> None:
        """Audit record contains all expected fields."""
        append_audit_log(_make_record(), tmp_path)
        content = (tmp_path / ".ac-guard" / "audit.jsonl").read_text()
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
        append_audit_log(record, tmp_path)
        content = (tmp_path / ".ac-guard" / "audit.jsonl").read_text()
        parsed = json.loads(content.strip())
        assert parsed["decision"] == "allow"
        assert parsed["reason"] is None

    def test_io_error_does_not_raise(self, tmp_path: Path) -> None:
        """I/O error does not raise exception."""
        (tmp_path / "readonly").mkdir()
        (tmp_path / "readonly").chmod(0o444)
        # This should not raise
        append_audit_log(_make_record(), tmp_path / "readonly")
        # Restore permissions for cleanup
        (tmp_path / "readonly").chmod(0o755)

    def test_custom_audit_path(self, tmp_path: Path) -> None:
        """Custom audit path is respected."""
        append_audit_log(_make_record(), tmp_path, "custom/audit.jsonl")
        assert (tmp_path / "custom" / "audit.jsonl").is_file()


class TestPolicyDecisionToAuditRecord:
    """Tests for PolicyDecision.to_audit_record()."""

    def test_deny_with_rule(self) -> None:
        """Deny decision produces correct audit record."""
        pd = PolicyDecision(
            decision=Decision.DENY,
            operation="write",
            scheme="file",
            target=".git/config",
            matched_rule=Rule(pattern="file:.git/**", reason="Git internals"),
            tier="forbidden",
            policy_hash="abcd1234",
        )
        record = pd.to_audit_record("Write", "claude-code")
        assert record["decision"] == "deny"
        assert record["reason"] == "Git internals"
        assert record["matched_rule"] == "file:.git/**"
        assert record["agent"] == "claude-code"
        assert record["tool"] == "Write"

    def test_allow_default(self) -> None:
        """Default allow produces null reason/pattern."""
        pd = PolicyDecision(
            decision=Decision.ALLOW,
            operation="write",
            scheme="file",
            target="src/main.py",
            matched_rule=None,
            tier="default",
            policy_hash="test",
        )
        record = pd.to_audit_record("Write", "claude-code")
        assert record["decision"] == "allow"
        assert record["reason"] is None
        assert record["matched_rule"] is None


class TestApplyRetention:
    """Tests for apply_retention function."""

    def test_removes_old_records(self, tmp_path: Path) -> None:
        """Records older than retention period are removed."""
        audit_path = tmp_path / ".ac-guard" / "audit.jsonl"
        audit_path.parent.mkdir(parents=True)

        old_ts = "2020-01-01T00:00:00+00:00"
        new_ts = datetime.now(tz=timezone.utc).isoformat()
        audit_path.write_text(
            json.dumps({"timestamp": old_ts, "decision": "deny"})
            + "\n"
            + json.dumps({"timestamp": new_ts, "decision": "allow"})
            + "\n",
        )

        removed = apply_retention(tmp_path, retention_days=30)
        assert removed == 1

        content = audit_path.read_text()
        records = [json.loads(line) for line in content.strip().split("\n")]
        assert len(records) == 1
        assert records[0]["decision"] == "allow"

    def test_retention_zero_keeps_all(self, tmp_path: Path) -> None:
        """retention_days=0 means keep forever."""
        audit_path = tmp_path / ".ac-guard" / "audit.jsonl"
        audit_path.parent.mkdir(parents=True)

        old_ts = "2020-01-01T00:00:00+00:00"
        audit_path.write_text(
            json.dumps({"timestamp": old_ts, "decision": "deny"}) + "\n",
        )

        removed = apply_retention(tmp_path, retention_days=0)
        assert removed == 0

    def test_no_file_returns_zero(self, tmp_path: Path) -> None:
        """No audit file returns 0 removed."""
        removed = apply_retention(tmp_path, retention_days=30)
        assert removed == 0
