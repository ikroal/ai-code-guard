"""Tests for generator data models."""

from __future__ import annotations

from datetime import datetime

from ai_guard.generator.models import (
    STATE_FILE,
    FileSpec,
    GeneratedState,
)


class TestFileSpec:
    """FileSpec dataclass tests."""

    def test_basic_construction(self) -> None:
        fs = FileSpec(path="test.txt", content="hello")
        assert fs.path == "test.txt"
        assert fs.content == "hello"
        assert fs.executable is False

    def test_executable_flag(self) -> None:
        fs = FileSpec(path="script.sh", content="#!/bin/bash", executable=True)
        assert fs.executable is True

    def test_defaults(self) -> None:
        fs = FileSpec(path="x", content="y")
        assert fs.executable is False


class TestGeneratedState:
    """GeneratedState dataclass and serialization tests."""

    def test_basic_construction(self) -> None:
        now = datetime.now()
        state = GeneratedState(
            ai_guard_version="0.1.0",
            installed_agents=["claude-code"],
            config_hash="abc123",
            installed_at=now,
            artifacts=["CLAUDE.md"],
        )
        assert state.ai_guard_version == "0.1.0"
        assert state.installed_agents == ["claude-code"]
        assert state.config_hash == "abc123"
        assert state.installed_at == now
        assert state.artifacts == ["CLAUDE.md"]

    def test_defaults(self) -> None:
        state = GeneratedState(ai_guard_version="0.1.0")
        assert state.installed_agents == []
        assert state.config_hash == ""
        assert state.artifacts == []

    def test_to_dict(self) -> None:
        now = datetime(2026, 4, 16, 12, 0, 0)
        state = GeneratedState(
            ai_guard_version="0.1.0",
            installed_agents=["claude-code", "cursor"],
            config_hash="abc123",
            installed_at=now,
            artifacts=["CLAUDE.md", ".claude/settings.json"],
        )
        d = state.to_dict()
        assert d["ai_guard_version"] == "0.1.0"
        assert d["installed_agents"] == ["claude-code", "cursor"]
        assert d["config_hash"] == "abc123"
        assert d["installed_at"] == "2026-04-16T12:00:00"
        assert d["artifacts"] == ["CLAUDE.md", ".claude/settings.json"]

    def test_to_json(self) -> None:
        state = GeneratedState(
            ai_guard_version="0.1.0",
            installed_agents=["claude-code"],
            config_hash="abc",
            installed_at=datetime(2026, 4, 16, 12, 0, 0),
            artifacts=["x"],
        )
        json_str = state.to_json()
        assert '"ai_guard_version": "0.1.0"' in json_str
        assert '"installed_agents"' in json_str

    def test_from_dict(self) -> None:
        d = {
            "ai_guard_version": "0.2.0",
            "installed_agents": ["cursor"],
            "config_hash": "def456",
            "installed_at": "2026-04-15T10:30:00",
            "artifacts": ["file1", "file2"],
        }
        state = GeneratedState.from_dict(d)
        assert state.ai_guard_version == "0.2.0"
        assert state.installed_agents == ["cursor"]
        assert state.config_hash == "def456"
        assert state.installed_at == datetime(2026, 4, 15, 10, 30, 0)
        assert state.artifacts == ["file1", "file2"]

    def test_from_dict_missing_fields(self) -> None:
        d = {"ai_guard_version": "0.1.0"}
        state = GeneratedState.from_dict(d)
        assert state.installed_agents == []
        assert state.config_hash == ""
        assert state.artifacts == []

    def test_json_roundtrip(self) -> None:
        original = GeneratedState(
            ai_guard_version="0.1.0",
            installed_agents=["claude-code", "cursor"],
            config_hash="abc123",
            installed_at=datetime(2026, 4, 16, 14, 30, 0),
            artifacts=["CLAUDE.md", ".cursor/rules/behavior.mdc"],
        )
        json_str = original.to_json()
        restored = GeneratedState.from_json(json_str)
        assert restored.ai_guard_version == original.ai_guard_version
        assert restored.installed_agents == original.installed_agents
        assert restored.config_hash == original.config_hash
        assert restored.installed_at == original.installed_at
        assert restored.artifacts == original.artifacts


class TestConstants:
    """Module constants tests."""

    def test_state_file_path(self) -> None:
        assert STATE_FILE == ".ai-guard/state.json"
