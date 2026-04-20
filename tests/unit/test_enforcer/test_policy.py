"""Tests for Enforcer policy loader (E1)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ac_guard.config.models import BehaviorConfig
from ac_guard.enforcer.exceptions import PolicyCorruptError
from ac_guard.enforcer.policy import load_policy


def _write_policy(project_root: Path, policy_data: dict) -> None:
    """Write a runtime.json file."""
    policy_dir = project_root / ".ac-guard"
    policy_dir.mkdir(parents=True, exist_ok=True)
    (policy_dir / "runtime.json").write_text(
        json.dumps(policy_data, indent=2), encoding="utf-8"
    )


class TestLoadPolicy:
    """Tests for load_policy function."""

    def test_no_policy_returns_none(self, tmp_path: Path) -> None:
        """Missing runtime.json returns None."""
        result = load_policy(tmp_path)
        assert result is None

    def test_corrupt_json_raises(self, tmp_path: Path) -> None:
        """Corrupted JSON raises PolicyCorruptError."""
        policy_dir = tmp_path / ".ac-guard"
        policy_dir.mkdir(parents=True)
        (policy_dir / "runtime.json").write_text("not valid json{{{", encoding="utf-8")
        with pytest.raises(PolicyCorruptError):
            load_policy(tmp_path)

    def test_loads_valid_policy(self, tmp_path: Path) -> None:
        """Valid runtime.json returns (BehaviorConfig, config_hash)."""
        _write_policy(
            tmp_path,
            {
                "config_hash": "abcd1234",
                "behavior": {
                    "read": {"forbidden": [], "require_approval": [], "allow": []},
                    "write": {"forbidden": [], "require_approval": [], "allow": []},
                    "execute": {"forbidden": [], "require_approval": [], "allow": []},
                },
            },
        )
        result = load_policy(tmp_path)
        assert result is not None
        behavior, config_hash, _audit = result
        assert isinstance(behavior, BehaviorConfig)
        assert config_hash == "abcd1234"

    def test_loads_rules(self, tmp_path: Path) -> None:
        """Policy rules are deserialized correctly."""
        _write_policy(
            tmp_path,
            {
                "config_hash": "test1234",
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
                    "execute": {"forbidden": [], "require_approval": [], "allow": []},
                },
            },
        )
        result = load_policy(tmp_path)
        assert result is not None
        behavior, _, _audit = result
        assert len(behavior.write.forbidden) == 1
        assert behavior.write.forbidden[0].pattern == "file:.git/**"
        assert behavior.write.forbidden[0].reason == "Git internals"
        assert len(behavior.write.require_approval) == 1
        assert len(behavior.write.allow) == 1

    def test_regex_flag_preserved(self, tmp_path: Path) -> None:
        """Regex flag on rules is preserved."""
        _write_policy(
            tmp_path,
            {
                "config_hash": "test",
                "behavior": {
                    "read": {"forbidden": [], "require_approval": [], "allow": []},
                    "write": {"forbidden": [], "require_approval": [], "allow": []},
                    "execute": {
                        "forbidden": [
                            {
                                "pattern": r"shell:git\s+push\s+--force.*",
                                "regex": True,
                                "source": "user",
                            },
                        ],
                        "require_approval": [],
                        "allow": [],
                    },
                },
            },
        )
        result = load_policy(tmp_path)
        assert result is not None
        behavior, _, _audit = result
        assert behavior.execute.forbidden[0].regex is True

    def test_empty_behavior(self, tmp_path: Path) -> None:
        """Empty behavior sections still work."""
        _write_policy(
            tmp_path,
            {
                "config_hash": "empty",
                "behavior": {
                    "read": {},
                    "write": {},
                    "execute": {},
                },
            },
        )
        result = load_policy(tmp_path)
        assert result is not None
        behavior, _, _audit = result
        assert behavior.read.forbidden == []

    def test_audit_section_parsed(self, tmp_path: Path) -> None:
        _write_policy(
            tmp_path,
            {
                "config_hash": "h",
                "behavior": {"read": {}, "write": {}, "execute": {}},
                "audit": {
                    "enabled": True,
                    "path": ".ac-guard/audit.jsonl",
                    "retention_days": 90,
                },
            },
        )
        result = load_policy(tmp_path)
        assert result is not None
        _, _, audit = result
        assert audit.enabled is True
        assert audit.path == ".ac-guard/audit.jsonl"
        assert audit.retention == 90

    def test_missing_audit_section_defaults_disabled(self, tmp_path: Path) -> None:
        """Legacy cache without audit section is loaded as disabled."""
        _write_policy(
            tmp_path,
            {
                "config_hash": "h",
                "behavior": {"read": {}, "write": {}, "execute": {}},
            },
        )
        result = load_policy(tmp_path)
        assert result is not None
        _, _, audit = result
        assert audit.enabled is False
