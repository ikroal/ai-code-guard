"""Tests for generator core functions."""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import pytest

from ai_guard.generator.core import (
    MARKER_BEGIN,
    MARKER_END,
    create_state,
    delete_artifacts,
    read_state,
    replace_managed_block,
    wrap_with_managed_block,
    write_artifacts,
    write_state,
)
from ai_guard.generator.exceptions import ArtifactWriteError
from ai_guard.generator.models import STATE_FILE, FileSpec, GeneratedState

# ---------------------------------------------------------------------------
# State Management Tests
# ---------------------------------------------------------------------------


class TestReadState:
    """read_state function tests."""

    def test_returns_none_when_file_missing(self, tmp_path: Path) -> None:
        result = read_state(tmp_path)
        assert result is None

    def test_returns_state_when_file_exists(self, tmp_path: Path) -> None:
        state_data = {
            "ai_guard_version": "0.1.0",
            "installed_agents": ["claude-code"],
            "config_hash": "abc123",
            "installed_at": "2026-04-16T12:00:00",
            "artifacts": ["CLAUDE.md"],
        }
        state_file = tmp_path / STATE_FILE
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text(json.dumps(state_data), encoding="utf-8")

        result = read_state(tmp_path)
        assert result is not None
        assert result.ai_guard_version == "0.1.0"
        assert result.installed_agents == ["claude-code"]

    def test_handles_empty_state_file(self, tmp_path: Path) -> None:
        state_file = tmp_path / STATE_FILE
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text("{}", encoding="utf-8")

        result = read_state(tmp_path)
        assert result is not None
        assert result.installed_agents == []


class TestWriteState:
    """write_state function tests."""

    def test_creates_ai_guard_directory(self, tmp_path: Path) -> None:
        state = GeneratedState(
            ai_guard_version="0.1.0",
            installed_agents=["claude-code"],
            config_hash="abc",
            installed_at=datetime.now(),
            artifacts=["x"],
        )
        write_state(tmp_path, state)
        assert (tmp_path / ".ai-guard").is_dir()
        assert (tmp_path / STATE_FILE).is_file()

    def test_writes_valid_json(self, tmp_path: Path) -> None:
        state = GeneratedState(
            ai_guard_version="0.1.0",
            installed_agents=["claude-code", "cursor"],
            config_hash="abc123",
            installed_at=datetime(2026, 4, 16, 14, 0, 0),
            artifacts=["CLAUDE.md", ".cursor/rules"],
        )
        write_state(tmp_path, state)

        content = (tmp_path / STATE_FILE).read_text(encoding="utf-8")
        data = json.loads(content)
        assert data["ai_guard_version"] == "0.1.0"
        assert data["installed_agents"] == ["claude-code", "cursor"]

    def test_overwrites_existing_state(self, tmp_path: Path) -> None:
        # Write initial state
        state1 = GeneratedState(
            ai_guard_version="0.1.0",
            installed_agents=["claude-code"],
            installed_at=datetime.now(),
        )
        write_state(tmp_path, state1)

        # Write updated state
        state2 = GeneratedState(
            ai_guard_version="0.1.0",
            installed_agents=["claude-code", "cursor"],
            installed_at=datetime.now(),
        )
        write_state(tmp_path, state2)

        result = read_state(tmp_path)
        assert result is not None
        assert result.installed_agents == ["claude-code", "cursor"]


class TestCreateState:
    """create_state function tests."""

    def test_creates_state_with_current_version(self) -> None:
        state = create_state(
            installed_agents=["claude-code"],
            config_hash="abc123",
            artifacts=["CLAUDE.md"],
        )
        assert state.ai_guard_version == "0.1.0"
        assert state.installed_agents == ["claude-code"]
        assert state.config_hash == "abc123"
        assert state.artifacts == ["CLAUDE.md"]
        # installed_at should be recent
        now = datetime.now()
        delta = now - state.installed_at
        assert delta.total_seconds() < 5


# ---------------------------------------------------------------------------
# Managed Block Tests
# ---------------------------------------------------------------------------


class TestWrapWithManagedBlock:
    """wrap_with_managed_block function tests."""

    def test_wraps_content(self) -> None:
        content = "This is managed content."
        result = wrap_with_managed_block(content)
        assert result.startswith(MARKER_BEGIN)
        assert result.endswith(MARKER_END + "\n")
        assert "This is managed content." in result

    def test_includes_both_markers(self) -> None:
        result = wrap_with_managed_block("test")
        assert MARKER_BEGIN in result
        assert MARKER_END in result
        # BEGIN should come before END
        assert result.find(MARKER_BEGIN) < result.find(MARKER_END)


class TestReplaceManagedBlock:
    """replace_managed_block function tests."""

    def test_replaces_content_inside_markers(self) -> None:
        existing = f"Header\n{MARKER_BEGIN}\nOld content\n{MARKER_END}\nFooter"
        new = "New content"
        result = replace_managed_block(existing, new)
        assert "Header" in result
        assert "Footer" in result
        assert "Old content" not in result
        assert "New content" in result

    def test_preserves_content_before_markers(self) -> None:
        existing = f"Keep this\n{MARKER_BEGIN}\nReplace this\n{MARKER_END}\n"
        result = replace_managed_block(existing, "New")
        assert "Keep this" in result

    def test_preserves_content_after_markers(self) -> None:
        existing = f"{MARKER_BEGIN}\nReplace\n{MARKER_END}\nKeep this too\n"
        result = replace_managed_block(existing, "New")
        assert "Keep this too" in result

    def test_appends_wrapped_content_when_markers_missing(self) -> None:
        existing = "Existing content without markers"
        result = replace_managed_block(existing, "New managed content")
        assert "Existing content without markers" in result
        assert MARKER_BEGIN in result
        assert MARKER_END in result
        assert "New managed content" in result

    def test_handles_empty_existing_content(self) -> None:
        result = replace_managed_block("", "New content")
        assert MARKER_BEGIN in result
        assert "New content" in result
        assert MARKER_END in result

    def test_handles_multiline_content(self) -> None:
        existing = f"{MARKER_BEGIN}\nLine 1\nLine 2\n{MARKER_END}\n"
        new = "New line A\nNew line B"
        result = replace_managed_block(existing, new)
        assert "New line A" in result
        assert "New line B" in result


# ---------------------------------------------------------------------------
# Artifact Writing Tests
# ---------------------------------------------------------------------------


class TestWriteArtifacts:
    """write_artifacts function tests."""

    def test_creates_files(self, tmp_path: Path) -> None:
        artifacts = [
            FileSpec(path="test.txt", content="hello"),
            FileSpec(path="subdir/nested.txt", content="nested content"),
        ]
        written = write_artifacts(tmp_path, artifacts)
        assert "test.txt" in written
        assert "subdir/nested.txt" in written
        assert (tmp_path / "test.txt").read_text() == "hello"
        assert (tmp_path / "subdir" / "nested.txt").read_text() == "nested content"

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        artifacts = [
            FileSpec(path="deep/path/to/file.txt", content="x"),
        ]
        write_artifacts(tmp_path, artifacts)
        assert (tmp_path / "deep" / "path" / "to" / "file.txt").is_file()

    def test_sets_executable_flag(self, tmp_path: Path) -> None:
        # Unix executable bits don't work on Windows
        if sys.platform == "win32":
            pytest.skip("Executable flag is Unix-specific")
        artifacts = [
            FileSpec(path="script.sh", content="#!/bin/bash", executable=True),
        ]
        write_artifacts(tmp_path, artifacts)
        file_path = tmp_path / "script.sh"
        # Check if file is executable (at least user-executable)
        mode = file_path.stat().st_mode
        assert mode & 0o111  # Any executable bit set

    def test_wraps_md_files_with_managed_block(self, tmp_path: Path) -> None:
        artifacts = [
            FileSpec(path="CLAUDE.md", content="# Rules\n\nDo this."),
        ]
        write_artifacts(tmp_path, artifacts)
        content = (tmp_path / "CLAUDE.md").read_text()
        assert MARKER_BEGIN in content
        assert MARKER_END in content
        assert "# Rules" in content

    def test_does_not_wrap_non_md_files(self, tmp_path: Path) -> None:
        artifacts = [
            FileSpec(path="config.yaml", content="key: value"),
        ]
        write_artifacts(tmp_path, artifacts)
        content = (tmp_path / "config.yaml").read_text()
        assert MARKER_BEGIN not in content
        assert content == "key: value"

    def test_replaces_managed_block_in_existing_file(self, tmp_path: Path) -> None:
        # Create existing file with managed block
        existing = f"User header\n{MARKER_BEGIN}\nOld rules\n{MARKER_END}\nUser footer"
        (tmp_path / "CLAUDE.md").write_text(existing)

        # Write new content
        artifacts = [
            FileSpec(path="CLAUDE.md", content="New rules"),
        ]
        write_artifacts(tmp_path, artifacts)

        content = (tmp_path / "CLAUDE.md").read_text()
        assert "User header" in content
        assert "User footer" in content
        assert "Old rules" not in content
        assert "New rules" in content

    def test_overwrites_file_without_markers(self, tmp_path: Path) -> None:
        # Create existing file without markers
        (tmp_path / "config.yaml").write_text("old: content")

        artifacts = [
            FileSpec(path="config.yaml", content="new: content"),
        ]
        write_artifacts(tmp_path, artifacts)

        content = (tmp_path / "config.yaml").read_text()
        assert content == "new: content"

    def test_dry_run_returns_paths_without_writing(self, tmp_path: Path) -> None:
        artifacts = [
            FileSpec(path="test.txt", content="hello"),
        ]
        written = write_artifacts(tmp_path, artifacts, dry_run=True)
        assert written == ["test.txt"]
        assert not (tmp_path / "test.txt").exists()

    def test_raises_artifact_write_error_on_permission_denied(
        self, tmp_path: Path
    ) -> None:
        # Windows doesn't support Unix-style permission restrictions
        if sys.platform == "win32":
            pytest.skip("Unix permission tests don't work on Windows")
        # This test is tricky on most systems; skip if we can't create
        # a permission-restricted directory
        if not tmp_path.exists():
            pytest.skip("Cannot test permission errors reliably")

        # Create a read-only directory (may not work on all platforms)
        readonly_dir = tmp_path / "readonly"
        readonly_dir.mkdir()
        try:
            readonly_dir.chmod(0o444)  # Read-only
        except OSError:
            pytest.skip("Cannot set directory permissions on this platform")

        try:
            artifacts = [
                FileSpec(path="readonly/test.txt", content="x"),
            ]
            with pytest.raises(ArtifactWriteError) as exc_info:
                write_artifacts(tmp_path, artifacts)
            assert "readonly/test.txt" in exc_info.value.failed_paths
        finally:
            # Restore permissions for cleanup
            readonly_dir.chmod(0o755)


class TestDeleteArtifacts:
    """delete_artifacts function tests."""

    def test_deletes_existing_files(self, tmp_path: Path) -> None:
        # Create some files
        (tmp_path / "file1.txt").write_text("x")
        (tmp_path / "subdir").mkdir()
        (tmp_path / "subdir" / "file2.txt").write_text("y")

        deleted = delete_artifacts(tmp_path, ["file1.txt", "subdir/file2.txt"])
        assert "file1.txt" in deleted
        assert "subdir/file2.txt" in deleted
        assert not (tmp_path / "file1.txt").exists()

    def test_skips_nonexistent_files(self, tmp_path: Path) -> None:
        deleted = delete_artifacts(tmp_path, ["nonexistent.txt"])
        assert deleted == []

    def test_returns_deleted_paths(self, tmp_path: Path) -> None:
        (tmp_path / "a.txt").write_text("x")
        (tmp_path / "b.txt").write_text("y")
        deleted = delete_artifacts(tmp_path, ["a.txt", "b.txt", "c.txt"])
        assert "a.txt" in deleted
        assert "b.txt" in deleted
        assert "c.txt" not in deleted


# ---------------------------------------------------------------------------
# Marker Constants Tests
# ---------------------------------------------------------------------------


class TestMarkerConstants:
    """Marker constant tests."""

    def test_marker_begin_format(self) -> None:
        assert MARKER_BEGIN == "<!-- AI-GUARD:BEGIN -->"

    def test_marker_end_format(self) -> None:
        assert MARKER_END == "<!-- AI-GUARD:END -->"
