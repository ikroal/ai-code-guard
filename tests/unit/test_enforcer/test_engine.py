"""Tests for Enforcer engine — top-level evaluate() (E1+E2+E3/E4)."""

from __future__ import annotations

import json
from pathlib import Path

from ac_guard.enforcer.engine import evaluate
from ac_guard.enforcer.matcher import Decision, PolicyDecision


def _write_policy(project_root: Path, policy_data: dict) -> None:
    """Write a runtime.json file."""
    policy_dir = project_root / ".ac-guard"
    policy_dir.mkdir(parents=True, exist_ok=True)
    (policy_dir / "runtime.json").write_text(
        json.dumps(policy_data, indent=2), encoding="utf-8"
    )


def _standard_policy() -> dict:
    """Return a realistic policy dict."""
    return {
        "config_hash": "abcd1234",
        "behavior": {
            "read": {
                "forbidden": [
                    {
                        "pattern": "file:**/.env",
                        "reason": "secrets",
                        "source": "default",
                    },
                ],
                "require_approval": [],
                "allow": [],
            },
            "write": {
                "forbidden": [
                    {
                        "pattern": "file:.git/**",
                        "reason": "Git internals",
                        "source": "default",
                    },
                ],
                "require_approval": [
                    {
                        "pattern": "file:guard.yaml",
                        "message": "Config change",
                        "source": "system",
                    },
                ],
                "allow": [
                    {"pattern": "file:src/**", "source": "user"},
                ],
            },
            "execute": {
                "forbidden": [
                    {
                        "pattern": "shell:git push --force*",
                        "reason": "No force push",
                        "source": "default",
                    },
                ],
                "require_approval": [],
                "allow": [
                    {"pattern": "shell:git status*", "source": "default"},
                ],
            },
        },
    }


class TestEvaluateNoPolicy:
    """Tests when no policy is installed."""

    def test_no_policy_allows_all(self, tmp_path: Path) -> None:
        """Without runtime.json, all operations are allowed."""
        result = evaluate("Write", {"file_path": ".git/config"}, tmp_path)
        assert result.decision == Decision.ALLOW
        assert result.tier == "no_policy"

    def test_corrupt_policy_denies(self, tmp_path: Path) -> None:
        """Corrupt runtime.json results in deny."""
        policy_dir = tmp_path / ".ac-guard"
        policy_dir.mkdir(parents=True)
        (policy_dir / "runtime.json").write_text("{{invalid json")
        result = evaluate("Write", {"file_path": "test.py"}, tmp_path)
        assert result.decision == Decision.DENY
        assert result.tier == "error"


class TestEvaluateFileOps:
    """Tests for file read/write evaluation."""

    def test_write_to_git_denied(self, tmp_path: Path) -> None:
        """Writing to .git/ is denied with full PolicyDecision fields."""
        _write_policy(tmp_path, _standard_policy())
        result = evaluate("Write", {"file_path": ".git/config"}, tmp_path)
        assert isinstance(result, PolicyDecision)
        assert result.decision == Decision.DENY
        assert result.operation == "write"
        assert result.scheme == "file"
        assert result.target == ".git/config"
        assert result.policy_hash == "abcd1234"

    def test_write_to_src_allowed(self, tmp_path: Path) -> None:
        """Writing to src/ is allowed."""
        _write_policy(tmp_path, _standard_policy())
        result = evaluate("Write", {"file_path": "src/main.py"}, tmp_path)
        assert result.decision == Decision.ALLOW
        assert result.tier == "allow"

    def test_write_to_config_asks(self, tmp_path: Path) -> None:
        """Writing to guard.yaml asks for approval."""
        _write_policy(tmp_path, _standard_policy())
        result = evaluate("Edit", {"file_path": "guard.yaml"}, tmp_path)
        assert result.decision == Decision.ASK

    def test_read_env_denied(self, tmp_path: Path) -> None:
        """Reading .env files is denied."""
        _write_policy(tmp_path, _standard_policy())
        result = evaluate("Read", {"file_path": "config/.env"}, tmp_path)
        assert result.decision == Decision.DENY

    def test_read_normal_file_allowed(self, tmp_path: Path) -> None:
        """Reading normal files is allowed (default)."""
        _write_policy(tmp_path, _standard_policy())
        result = evaluate("Read", {"file_path": "src/main.py"}, tmp_path)
        assert result.decision == Decision.ALLOW


class TestEvaluateShellOps:
    """Tests for shell command evaluation."""

    def test_force_push_denied(self, tmp_path: Path) -> None:
        """Force push is denied."""
        _write_policy(tmp_path, _standard_policy())
        result = evaluate("Bash", {"command": "git push --force origin"}, tmp_path)
        assert result.decision == Decision.DENY

    def test_git_status_allowed(self, tmp_path: Path) -> None:
        """Git status is allowed."""
        _write_policy(tmp_path, _standard_policy())
        result = evaluate("Bash", {"command": "git status"}, tmp_path)
        assert result.decision == Decision.ALLOW

    def test_unknown_command_default_allow(self, tmp_path: Path) -> None:
        """Unknown commands get default allow."""
        _write_policy(tmp_path, _standard_policy())
        result = evaluate("Bash", {"command": "npm install"}, tmp_path)
        assert result.decision == Decision.ALLOW
        assert result.tier == "default"


class TestEvaluateUnknownTool:
    """Tests for unknown tool handling."""

    def test_unknown_tool_allowed(self, tmp_path: Path) -> None:
        """Unknown tools are allowed."""
        _write_policy(tmp_path, _standard_policy())
        result = evaluate("SomeFutureTool", {"arg": "val"}, tmp_path)
        assert result.decision == Decision.ALLOW
        assert result.tier == "unknown_tool"


def _policy_with_audit(enabled: bool) -> dict:
    policy = _standard_policy()
    policy["audit"] = {
        "enabled": enabled,
        "path": ".ac-guard/audit.jsonl",
        "retention_days": 30,
    }
    return policy


class TestEvaluateAuditWiring:
    """Regression for #75: evaluate() writes audit when enabled."""

    def test_writes_audit_when_enabled(self, tmp_path: Path) -> None:
        _write_policy(tmp_path, _policy_with_audit(enabled=True))
        evaluate(
            "Write",
            {"file_path": "guard.yaml"},
            tmp_path,
            agent="claude-code",
        )
        audit_path = tmp_path / ".ac-guard" / "audit.jsonl"
        assert audit_path.is_file()
        lines = audit_path.read_text().strip().split("\n")
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["agent"] == "claude-code"
        assert record["tool"] == "Write"
        assert record["decision"] == "ask"

    def test_does_not_audit_when_disabled(self, tmp_path: Path) -> None:
        _write_policy(tmp_path, _policy_with_audit(enabled=False))
        evaluate(
            "Write",
            {"file_path": "guard.yaml"},
            tmp_path,
            agent="claude-code",
        )
        audit_path = tmp_path / ".ac-guard" / "audit.jsonl"
        assert not audit_path.exists()

    def test_missing_audit_section_defaults_disabled(self, tmp_path: Path) -> None:
        """Legacy runtime.json without an audit section is treated as off."""
        _write_policy(tmp_path, _standard_policy())
        evaluate(
            "Write",
            {"file_path": "guard.yaml"},
            tmp_path,
            agent="claude-code",
        )
        audit_path = tmp_path / ".ac-guard" / "audit.jsonl"
        assert not audit_path.exists()

    def test_unknown_tool_skips_audit(self, tmp_path: Path) -> None:
        """Early return on unknown_tool must not write audit."""
        _write_policy(tmp_path, _policy_with_audit(enabled=True))
        evaluate("SomeFutureTool", {"arg": "val"}, tmp_path, agent="claude-code")
        audit_path = tmp_path / ".ac-guard" / "audit.jsonl"
        assert not audit_path.exists()

    def test_passes_agent_to_record(self, tmp_path: Path) -> None:
        _write_policy(tmp_path, _policy_with_audit(enabled=True))
        evaluate("Write", {"file_path": "guard.yaml"}, tmp_path, agent="cursor")
        audit_path = tmp_path / ".ac-guard" / "audit.jsonl"
        record = json.loads(audit_path.read_text().strip().split("\n")[0])
        assert record["agent"] == "cursor"
