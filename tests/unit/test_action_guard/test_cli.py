"""Tests for Action guard CLI entry point."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _run_action_guard(input_data: dict, project_root: Path) -> dict:
    """Run action_guard CLI via subprocess and return parsed output."""
    input_data["project_root"] = str(project_root)
    result = subprocess.run(
        [sys.executable, "-m", "ac_guard.action_guard"],
        input=json.dumps(input_data),
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, f"CLI failed: {result.stderr}"
    return json.loads(result.stdout.strip())


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
            "read": {"forbidden": [], "require_approval": [], "allow": []},
            "write": {
                "forbidden": [
                    {
                        "pattern": "file:.git/**",
                        "reason": "Git internals",
                        "source": "default",
                    },
                ],
                "require_approval": [],
                "allow": [
                    {"pattern": "file:src/**", "source": "user"},
                ],
            },
            "execute": {"forbidden": [], "require_approval": [], "allow": []},
        },
    }


class TestActionGuardCli:
    """Tests for python3 -m ac_guard.action_guard."""

    def test_no_policy_allows(self, tmp_path: Path) -> None:
        """No runtime.json returns allow."""
        result = _run_action_guard(
            {"tool_name": "Write", "tool_input": {"file_path": ".git/config"}},
            tmp_path,
        )
        assert result["decision"] == "allow"

    def test_forbidden_denies(self, tmp_path: Path) -> None:
        """Forbidden pattern returns deny with reason."""
        _write_policy(tmp_path, _standard_policy())
        result = _run_action_guard(
            {"tool_name": "Write", "tool_input": {"file_path": ".git/config"}},
            tmp_path,
        )
        assert result["decision"] == "deny"
        assert "reason" in result

    def test_allowed_allows(self, tmp_path: Path) -> None:
        """Allowed pattern returns allow."""
        _write_policy(tmp_path, _standard_policy())
        result = _run_action_guard(
            {"tool_name": "Write", "tool_input": {"file_path": "src/main.py"}},
            tmp_path,
        )
        assert result["decision"] == "allow"

    def test_invalid_json_denies(self, tmp_path: Path) -> None:
        """Invalid JSON input returns deny (fail-closed)."""
        result = subprocess.run(
            [sys.executable, "-m", "ac_guard.action_guard"],
            input="not json{{{",
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        output = json.loads(result.stdout.strip())
        assert output["decision"] == "deny"


class TestActionGuardCliAudit:
    """Regression for #75: subprocess entry threads agent into audit."""

    def test_agent_from_stdin_is_recorded(self, tmp_path: Path) -> None:
        policy = _standard_policy()
        policy["audit"] = {
            "enabled": True,
            "path": ".ac-guard/audit.jsonl",
            "retention_days": 30,
        }
        _write_policy(tmp_path, policy)
        _run_action_guard(
            {
                "tool_name": "Write",
                "tool_input": {"file_path": ".git/config"},
                "agent": "opencode",
            },
            tmp_path,
        )
        audit_path = tmp_path / ".ac-guard" / "audit.jsonl"
        assert audit_path.is_file()
        record = json.loads(
            audit_path.read_text(encoding="utf-8").strip().split("\n")[0]
        )
        assert record["agent"] == "opencode"
