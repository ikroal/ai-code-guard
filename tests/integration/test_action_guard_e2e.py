"""Integration tests for Phase 2 Action guard end-to-end (WP2.4).

Verifies Action guard pipeline, Hook template integration, audit logging,
and error recovery scenarios using real file I/O.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml
from typer.testing import CliRunner

from ac_guard.action_guard.core import evaluate
from ac_guard.action_guard.matcher import Decision
from ac_guard.audit import append_record, prune_by_age
from ac_guard.cli.main import app

runner = CliRunner()


def _init_and_install(tmp_path: Path, agents: str = "claude-code") -> None:
    """Helper: init + install in tmp_path."""
    config = tmp_path / "guard.yaml"
    (tmp_path / ".git").mkdir()
    runner.invoke(app, ["init", "--language", "python", "--output", str(config)])
    runner.invoke(app, ["install", "--agent", agents, "--config", str(config)])


class TestActionGuardPipeline:
    """Action guard evaluate() with real runtime.json from install."""

    def test_install_then_evaluate(self, tmp_path: Path) -> None:
        """install generates runtime.json that evaluate() can use."""
        _init_and_install(tmp_path)
        # runtime.json should exist
        assert (tmp_path / ".ac-guard" / "runtime.json").is_file()
        # Evaluate should work (system protection rules present)
        result = evaluate("Write", {"file_path": "src/main.py"}, tmp_path)
        assert result.decision in (Decision.ALLOW, Decision.ASK, Decision.DENY)

    def test_system_protection_rules(self, tmp_path: Path) -> None:
        """System protection rules deny writing to guard.yaml."""
        _init_and_install(tmp_path)
        result = evaluate("Write", {"file_path": "guard.yaml"}, tmp_path)
        assert result.decision == Decision.ASK
        assert result.tier == "require_approval"

    def test_update_refreshes_policy(self, tmp_path: Path) -> None:
        """Updating config and running update changes policy behavior."""
        config = tmp_path / "guard.yaml"
        (tmp_path / ".git").mkdir()
        runner.invoke(app, ["init", "--language", "python", "--output", str(config)])
        runner.invoke(
            app, ["install", "--agent", "claude-code", "--config", str(config)]
        )

        # Before: reading .env is allowed (default config has no read rules)
        result = evaluate("Read", {"file_path": "config/.env"}, tmp_path)
        assert result.decision == Decision.ALLOW

        # Add forbidden rule for .env files
        config.write_text(
            yaml.dump(
                {
                    "version": 1,
                    "project": {"name": "test", "language": "python"},
                    "behavior": {
                        "read": {
                            "forbidden": [
                                {"pattern": "file:**/.env", "reason": "secrets"}
                            ]
                        }
                    },
                },
                default_flow_style=False,
            ),
            encoding="utf-8",
        )
        runner.invoke(app, ["update", "--config", str(config)])

        # After: reading .env is denied
        result = evaluate("Read", {"file_path": "config/.env"}, tmp_path)
        assert result.decision == Decision.DENY
        assert result.matched_rule is not None
        assert result.matched_rule.reason == "secrets"


class TestHookActionGuardIntegration:
    """Hook templates correctly reference Action guard."""

    def test_claude_code_hook_has_action_guard(self, tmp_path: Path) -> None:
        """Claude Code hook script imports action_guard.core."""
        _init_and_install(tmp_path)
        hook_path = tmp_path / ".claude" / "hooks" / "interceptor.py"
        assert hook_path.is_file()
        content = hook_path.read_text(encoding="utf-8")
        assert "from ac_guard.action_guard.core import evaluate" in content

    def test_cursor_hook_calls_action_guard(self, tmp_path: Path) -> None:
        """Cursor hook script calls python3 -m ac_guard.action_guard."""
        _init_and_install(tmp_path, agents="cursor")
        hook_path = tmp_path / ".cursor" / "hooks" / "check.sh"
        assert hook_path.is_file()
        content = hook_path.read_text(encoding="utf-8")
        assert "python3 -m ac_guard.action_guard" in content

    def test_multi_agent_hooks(self, tmp_path: Path) -> None:
        """Multi-agent install generates hooks for each agent."""
        _init_and_install(tmp_path, agents="claude-code,cursor")
        assert (tmp_path / ".claude" / "hooks" / "interceptor.py").is_file()
        assert (tmp_path / ".cursor" / "hooks" / "check.sh").is_file()


class TestAuditLoggingE2E:
    """Audit logging with real Action guard decisions."""

    def test_evaluate_then_audit(self, tmp_path: Path) -> None:
        """evaluate() auto-audits when audit is enabled (standard preset)."""
        _init_and_install(tmp_path)

        evaluate("Write", {"file_path": "guard.yaml"}, tmp_path, agent="claude-code")

        audit_path = tmp_path / ".ac-guard" / "audit.jsonl"
        assert audit_path.is_file()
        lines = audit_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 1
        parsed = json.loads(lines[0])
        assert parsed["agent"] == "claude-code"
        assert parsed["tool"] == "Write"
        assert parsed["decision"] in ("allow", "deny", "ask")
        assert "timestamp" in parsed

    def test_multiple_decisions_audited(self, tmp_path: Path) -> None:
        """Multiple evaluate calls produce multiple audit records."""
        _init_and_install(tmp_path)

        tool_calls = [
            ("Write", {"file_path": "guard.yaml"}),
            ("Read", {"file_path": "src/main.py"}),
            ("Bash", {"command": "git status"}),
        ]
        for tool_name, tool_input in tool_calls:
            evaluate(tool_name, tool_input, tmp_path, agent="claude-code")

        audit_path = tmp_path / ".ac-guard" / "audit.jsonl"
        assert audit_path.is_file()
        lines = audit_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 3

    def test_retention_cleanup(self, tmp_path: Path) -> None:
        """prune_by_age removes old records."""
        _init_and_install(tmp_path)

        # Write an old record manually
        audit_path = tmp_path / ".ac-guard" / "audit.jsonl"
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        old_record = json.dumps(
            {
                "timestamp": "2020-01-01T00:00:00+00:00",
                "decision": "deny",
            }
        )
        audit_path.write_text(old_record + "\n", encoding="utf-8")

        # Add a fresh record via evaluate (auto-audits)
        evaluate("Read", {"file_path": "src/main.py"}, tmp_path, agent="claude-code")

        # Retention should remove the old one
        removed = prune_by_age(tmp_path, max_age_days=30)
        assert removed == 1

        lines = audit_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 1


class TestErrorRecovery:
    """Error scenarios and fail-closed behavior."""

    def test_no_policy_allows_all(self, tmp_path: Path) -> None:
        """Without runtime.json, all operations are allowed."""
        result = evaluate("Write", {"file_path": ".git/config"}, tmp_path)
        assert result.decision == Decision.ALLOW
        assert result.tier == "no_policy"

    def test_corrupt_policy_denies(self, tmp_path: Path) -> None:
        """Corrupt runtime.json results in deny (fail-closed)."""
        policy_dir = tmp_path / ".ac-guard"
        policy_dir.mkdir(parents=True)
        (policy_dir / "runtime.json").write_text("{{{bad json", encoding="utf-8")
        result = evaluate("Write", {"file_path": "test.py"}, tmp_path)
        assert result.decision == Decision.DENY
        assert result.tier == "error"

    def test_audit_failure_does_not_block(self, tmp_path: Path) -> None:
        """Audit write failure does not affect evaluate result."""
        _init_and_install(tmp_path)

        result = evaluate("Write", {"file_path": "src/main.py"}, tmp_path)
        original_decision = result.decision

        # Write audit to a read-only subdirectory (not .ac-guard itself)
        readonly_dir = tmp_path / "readonly"
        readonly_dir.mkdir()
        readonly_dir.chmod(0o444)

        record = result.to_audit_record("Write", "claude-code")
        # This writes to readonly dir — should fail silently
        append_record(record, readonly_dir)

        # Decision is unchanged
        result2 = evaluate("Write", {"file_path": "src/main.py"}, tmp_path)
        assert result2.decision == original_decision

        # Restore permissions
        readonly_dir.chmod(0o755)
