"""Tests for generator data models.

FileSpec tests live in tests/unit/test_domain/test_models.py — FileSpec is
a domain-layer DTO, not a generator-specific type.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from ac_guard.generator import Installation, installation_path


class TestInstallation:
    """Installation dataclass and serialization tests."""

    def test_basic_construction(self) -> None:
        now = datetime.now()
        inst = Installation(
            ac_guard_version="0.1.0",
            installed_agents=["claude-code"],
            config_hash="abc123",
            installed_at=now,
            artifacts=["CLAUDE.md"],
        )
        assert inst.ac_guard_version == "0.1.0"
        assert inst.installed_agents == ["claude-code"]
        assert inst.config_hash == "abc123"
        assert inst.installed_at == now
        assert inst.artifacts == ["CLAUDE.md"]

    def test_defaults(self) -> None:
        inst = Installation(ac_guard_version="0.1.0")
        assert inst.installed_agents == []
        assert inst.config_hash == ""
        assert inst.artifacts == []

    def test_to_dict(self) -> None:
        now = datetime(2026, 4, 16, 12, 0, 0)
        inst = Installation(
            ac_guard_version="0.1.0",
            installed_agents=["claude-code", "opencode"],
            config_hash="abc123",
            installed_at=now,
            artifacts=["CLAUDE.md", ".claude/settings.json"],
        )
        d = inst.to_dict()
        assert d["ac_guard_version"] == "0.1.0"
        assert d["installed_agents"] == ["claude-code", "opencode"]
        assert d["config_hash"] == "abc123"
        assert d["installed_at"] == "2026-04-16T12:00:00"
        assert d["artifacts"] == ["CLAUDE.md", ".claude/settings.json"]

    def test_to_json(self) -> None:
        inst = Installation(
            ac_guard_version="0.1.0",
            installed_agents=["claude-code"],
            config_hash="abc",
            installed_at=datetime(2026, 4, 16, 12, 0, 0),
            artifacts=["x"],
        )
        json_str = inst.to_json()
        assert '"ac_guard_version": "0.1.0"' in json_str
        assert '"installed_agents"' in json_str

    def test_from_dict(self) -> None:
        d = {
            "ac_guard_version": "0.2.0",
            "installed_agents": ["opencode"],
            "config_hash": "def456",
            "installed_at": "2026-04-15T10:30:00",
            "artifacts": ["file1", "file2"],
        }
        inst = Installation.from_dict(d)
        assert inst.ac_guard_version == "0.2.0"
        assert inst.installed_agents == ["opencode"]
        assert inst.config_hash == "def456"
        assert inst.installed_at == datetime(2026, 4, 15, 10, 30, 0)
        assert inst.artifacts == ["file1", "file2"]

    def test_from_dict_missing_fields(self) -> None:
        d = {"ac_guard_version": "0.1.0"}
        inst = Installation.from_dict(d)
        assert inst.installed_agents == []
        assert inst.config_hash == ""
        assert inst.artifacts == []

    def test_json_roundtrip(self) -> None:
        original = Installation(
            ac_guard_version="0.1.0",
            installed_agents=["claude-code", "opencode"],
            config_hash="abc123",
            installed_at=datetime(2026, 4, 16, 14, 30, 0),
            artifacts=["CLAUDE.md", "AGENTS.md"],
        )
        json_str = original.to_json()
        restored = Installation.from_json(json_str)
        assert restored.ac_guard_version == original.ac_guard_version
        assert restored.installed_agents == original.installed_agents
        assert restored.config_hash == original.config_hash
        assert restored.installed_at == original.installed_at
        assert restored.artifacts == original.artifacts


class TestInstallationPath:
    """``installation_path`` returns the project-relative state file path."""

    def test_returns_under_ac_guard_dir(self, tmp_path: Path) -> None:
        result = installation_path(tmp_path)
        assert result == tmp_path / ".ac-guard" / "state.json"

    def test_does_not_create_directory(self, tmp_path: Path) -> None:
        """Computing the path must be side-effect free."""
        installation_path(tmp_path)
        assert not (tmp_path / ".ac-guard").exists()

    def test_idempotent(self, tmp_path: Path) -> None:
        assert installation_path(tmp_path) == installation_path(tmp_path)
