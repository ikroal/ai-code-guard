"""Tests for generator core functions."""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import pytest

from ac_guard.config.models import (
    BehaviorConfig,
    CheckItem,
    CodeConfig,
    LanguageTools,
    OperationRules,
    Rule,
    StageBucket,
)
from ac_guard.domain import (
    MARKER_BEGIN,
    MARKER_BEGIN_HASH,
    MARKER_END,
    MARKER_END_HASH,
    FileSpec,
)
from ac_guard.generator.core import (
    create_state,
    delete_artifacts,
    generate_git_hooks,
    generate_policy_cache,
    generate_precommit_config,
    generate_tool_configs,
    read_state,
    replace_managed_block,
    write_artifacts,
    write_state,
)
from ac_guard.generator.exceptions import ArtifactWriteError
from ac_guard.generator.models import STATE_FILE, GeneratedState

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
            "ac_guard_version": "0.1.0",
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
        assert result.ac_guard_version == "0.1.0"
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

    def test_creates_ac_guard_directory(self, tmp_path: Path) -> None:
        state = GeneratedState(
            ac_guard_version="0.1.0",
            installed_agents=["claude-code"],
            config_hash="abc",
            installed_at=datetime.now(),
            artifacts=["x"],
        )
        write_state(tmp_path, state)
        assert (tmp_path / ".ac-guard").is_dir()
        assert (tmp_path / STATE_FILE).is_file()

    def test_writes_valid_json(self, tmp_path: Path) -> None:
        state = GeneratedState(
            ac_guard_version="0.1.0",
            installed_agents=["claude-code", "cursor"],
            config_hash="abc123",
            installed_at=datetime(2026, 4, 16, 14, 0, 0),
            artifacts=["CLAUDE.md", ".cursor/rules"],
        )
        write_state(tmp_path, state)

        content = (tmp_path / STATE_FILE).read_text(encoding="utf-8")
        data = json.loads(content)
        assert data["ac_guard_version"] == "0.1.0"
        assert data["installed_agents"] == ["claude-code", "cursor"]

    def test_overwrites_existing_state(self, tmp_path: Path) -> None:
        # Write initial state
        state1 = GeneratedState(
            ac_guard_version="0.1.0",
            installed_agents=["claude-code"],
            installed_at=datetime.now(),
        )
        write_state(tmp_path, state1)

        # Write updated state
        state2 = GeneratedState(
            ac_guard_version="0.1.0",
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
        assert state.ac_guard_version == "0.1.0"
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
# wrap_with_markers is exercised by tests/unit/test_domain/test_models.py —
# this suite focuses on replace_managed_block, which is generator-specific.


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
        assert (tmp_path / "test.txt").read_text(encoding="utf-8") == "hello"
        assert (tmp_path / "subdir" / "nested.txt").read_text(
            encoding="utf-8"
        ) == "nested content"

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
        content = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
        assert MARKER_BEGIN in content
        assert MARKER_END in content
        assert "# Rules" in content

    def test_does_not_wrap_non_md_files(self, tmp_path: Path) -> None:
        artifacts = [
            FileSpec(path="config.yaml", content="key: value"),
        ]
        write_artifacts(tmp_path, artifacts)
        content = (tmp_path / "config.yaml").read_text(encoding="utf-8")
        assert MARKER_BEGIN not in content
        assert content == "key: value"

    def test_replaces_managed_block_in_existing_file(self, tmp_path: Path) -> None:
        # Create existing file with managed block
        existing = f"User header\n{MARKER_BEGIN}\nOld rules\n{MARKER_END}\nUser footer"
        (tmp_path / "CLAUDE.md").write_text(existing, encoding="utf-8")

        # Write new content
        artifacts = [
            FileSpec(path="CLAUDE.md", content="New rules"),
        ]
        write_artifacts(tmp_path, artifacts)

        content = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
        assert "User header" in content
        assert "User footer" in content
        assert "Old rules" not in content
        assert "New rules" in content

    def test_overwrites_file_without_markers(self, tmp_path: Path) -> None:
        # Create existing file without markers
        (tmp_path / "config.yaml").write_text("old: content", encoding="utf-8")

        artifacts = [
            FileSpec(path="config.yaml", content="new: content"),
        ]
        write_artifacts(tmp_path, artifacts)

        content = (tmp_path / "config.yaml").read_text(encoding="utf-8")
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


class TestMarkerDuplication:
    """Regression: install + repeated updates must not accumulate markers."""

    @staticmethod
    def _count(content: str, marker: str) -> int:
        return content.count(marker)

    def test_install_produces_single_marker_pair(self, tmp_path: Path) -> None:
        """First-time write of a .md artifact yields exactly one BEGIN/END pair."""
        artifact = FileSpec(path="CLAUDE.md", content="# Rules\n\nDo this.")
        write_artifacts(tmp_path, [artifact])
        content = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
        assert self._count(content, MARKER_BEGIN) == 1
        assert self._count(content, MARKER_END) == 1
        assert "# Rules" in content

    def test_update_preserves_single_marker_pair(self, tmp_path: Path) -> None:
        """A second write (update) still leaves exactly one BEGIN/END pair."""
        write_artifacts(tmp_path, [FileSpec(path="CLAUDE.md", content="v1")])
        write_artifacts(tmp_path, [FileSpec(path="CLAUDE.md", content="v2")])
        content = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
        assert self._count(content, MARKER_BEGIN) == 1
        assert self._count(content, MARKER_END) == 1
        assert "v2" in content
        assert "v1" not in content

    def test_install_wraps_mdc_rule_docs_too(self, tmp_path: Path) -> None:
        """Cursor uses .mdc; it must be wrapped like .md."""
        write_artifacts(
            tmp_path,
            [FileSpec(path=".cursor/rules/behavior.mdc", content="raw")],
        )
        content = (tmp_path / ".cursor" / "rules" / "behavior.mdc").read_text(
            encoding="utf-8"
        )
        assert self._count(content, MARKER_BEGIN) == 1
        assert self._count(content, MARKER_END) == 1

    def test_update_preserves_user_content_outside_markers(
        self, tmp_path: Path
    ) -> None:
        """User content added outside markers survives the next update."""
        write_artifacts(tmp_path, [FileSpec(path="CLAUDE.md", content="v1")])
        md = tmp_path / "CLAUDE.md"
        md.write_text(
            md.read_text(encoding="utf-8") + "\n\n## My Custom Section\nuser notes\n",
            encoding="utf-8",
        )
        write_artifacts(tmp_path, [FileSpec(path="CLAUDE.md", content="v2")])
        content = md.read_text(encoding="utf-8")
        assert self._count(content, MARKER_BEGIN) == 1
        assert self._count(content, MARKER_END) == 1
        assert "My Custom Section" in content
        assert "user notes" in content
        assert "v2" in content

    def test_rule_doc_round_trip_preserves_non_ascii(self, tmp_path: Path) -> None:
        """Non-ASCII content (em-dash, CJK) round-trips cleanly through write+read.

        Regression for #108: on Windows, `Path.read_text()` without an
        explicit encoding defaults to cp1252 and blows up on any
        non-ASCII bytes. This test catches both sides: that the
        generator writes UTF-8 and that we read it back with the same
        encoding.
        """
        body = "# Rules — 规则\n\n禁止 `git push --force`。"
        write_artifacts(tmp_path, [FileSpec(path="CLAUDE.md", content=body)])
        content = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
        assert "规则" in content
        assert "禁止" in content
        assert "—" in content


class TestDeleteArtifacts:
    """delete_artifacts function tests."""

    def test_deletes_existing_files(self, tmp_path: Path) -> None:
        # Create some files
        (tmp_path / "file1.txt").write_text("x", encoding="utf-8")
        (tmp_path / "subdir").mkdir()
        (tmp_path / "subdir" / "file2.txt").write_text("y", encoding="utf-8")

        deleted = delete_artifacts(tmp_path, ["file1.txt", "subdir/file2.txt"])
        assert "file1.txt" in deleted
        assert "subdir/file2.txt" in deleted
        assert not (tmp_path / "file1.txt").exists()

    def test_skips_nonexistent_files(self, tmp_path: Path) -> None:
        deleted = delete_artifacts(tmp_path, ["nonexistent.txt"])
        assert deleted == []

    def test_returns_deleted_paths(self, tmp_path: Path) -> None:
        (tmp_path / "a.txt").write_text("x", encoding="utf-8")
        (tmp_path / "b.txt").write_text("y", encoding="utf-8")
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


# ---------------------------------------------------------------------------
# G5: Policy Cache Tests
# ---------------------------------------------------------------------------


class TestGeneratePolicyCache:
    """generate_policy_cache function tests."""

    def test_returns_file_spec(self) -> None:
        behavior = BehaviorConfig.empty()
        result = generate_policy_cache(behavior, "abc123")
        assert isinstance(result, FileSpec)
        assert result.path == ".ac-guard/runtime.json"

    def test_includes_config_hash(self) -> None:
        behavior = BehaviorConfig.empty()
        result = generate_policy_cache(behavior, "test_hash")
        data = json.loads(result.content)
        assert data["config_hash"] == "test_hash"

    def test_serializes_empty_behavior(self) -> None:
        behavior = BehaviorConfig.empty()
        result = generate_policy_cache(behavior, "hash")
        data = json.loads(result.content)
        assert "behavior" in data
        assert data["behavior"]["read"]["forbidden"] == []
        assert data["behavior"]["write"]["forbidden"] == []
        assert data["behavior"]["execute"]["forbidden"] == []

    def test_serializes_rules(self) -> None:
        behavior = BehaviorConfig(
            read=OperationRules(
                forbidden=[
                    Rule(pattern="file:.env", reason="secrets", source="user"),
                ],
                require_approval=[],
                allow=[],
            ),
            write=OperationRules.empty(),
            execute=OperationRules.empty(),
        )
        result = generate_policy_cache(behavior, "hash")
        data = json.loads(result.content)
        assert data["behavior"]["read"]["forbidden"][0]["pattern"] == "file:.env"
        assert data["behavior"]["read"]["forbidden"][0]["reason"] == "secrets"
        assert data["behavior"]["read"]["forbidden"][0]["source"] == "user"

    def test_omits_optional_fields_when_none(self) -> None:
        behavior = BehaviorConfig(
            read=OperationRules(
                forbidden=[Rule(pattern="file:test", source="default")],
                require_approval=[],
                allow=[],
            ),
            write=OperationRules.empty(),
            execute=OperationRules.empty(),
        )
        result = generate_policy_cache(behavior, "hash")
        data = json.loads(result.content)
        rule = data["behavior"]["read"]["forbidden"][0]
        assert "reason" not in rule
        assert "message" not in rule
        assert "regex" not in rule

    def test_runtime_cache_includes_audit_section(self) -> None:
        from ac_guard.config.models import AuditConfig

        behavior = BehaviorConfig.empty()
        audit = AuditConfig(enabled=True, path=".ac-guard/audit.jsonl", retention=60)
        result = generate_policy_cache(behavior, "hash", audit=audit)
        data = json.loads(result.content)
        assert data["audit"] == {
            "enabled": True,
            "path": ".ac-guard/audit.jsonl",
            "retention_days": 60,
        }

    def test_runtime_cache_omits_audit_when_none(self) -> None:
        behavior = BehaviorConfig.empty()
        result = generate_policy_cache(behavior, "hash")
        data = json.loads(result.content)
        assert "audit" not in data

    def test_includes_regex_flag(self) -> None:
        behavior = BehaviorConfig(
            read=OperationRules(
                forbidden=[Rule(pattern="regex:test", regex=True, source="user")],
                require_approval=[],
                allow=[],
            ),
            write=OperationRules.empty(),
            execute=OperationRules.empty(),
        )
        result = generate_policy_cache(behavior, "hash")
        data = json.loads(result.content)
        rule = data["behavior"]["read"]["forbidden"][0]
        assert rule["regex"] is True


# ---------------------------------------------------------------------------
# G6: Git Hooks Tests
# ---------------------------------------------------------------------------


class TestGenerateGitHooks:
    """generate_git_hooks function tests."""

    def test_returns_empty_list_when_git_missing(self, tmp_path: Path) -> None:
        result = generate_git_hooks(tmp_path)
        assert result == []

    def test_returns_hooks_when_git_exists(self, tmp_path: Path) -> None:
        (tmp_path / ".git").mkdir()
        (tmp_path / ".git" / "hooks").mkdir()
        result = generate_git_hooks(tmp_path)
        assert len(result) == 2

    def test_hooks_have_correct_paths(self, tmp_path: Path) -> None:
        (tmp_path / ".git").mkdir()
        (tmp_path / ".git" / "hooks").mkdir()
        result = generate_git_hooks(tmp_path)
        paths = [a.path for a in result]
        assert ".git/hooks/pre-commit" in paths
        assert ".git/hooks/pre-push" in paths

    def test_hooks_are_executable(self, tmp_path: Path) -> None:
        (tmp_path / ".git").mkdir()
        (tmp_path / ".git" / "hooks").mkdir()
        result = generate_git_hooks(tmp_path)
        for hook in result:
            assert hook.executable is True

    def test_hooks_contain_guard_command(self, tmp_path: Path) -> None:
        (tmp_path / ".git").mkdir()
        (tmp_path / ".git" / "hooks").mkdir()
        result = generate_git_hooks(tmp_path)
        for hook in result:
            assert "ac-guard gate run" in hook.content

    def test_pre_commit_has_correct_stage(self, tmp_path: Path) -> None:
        (tmp_path / ".git").mkdir()
        (tmp_path / ".git" / "hooks").mkdir()
        result = generate_git_hooks(tmp_path)
        pre_commit = next(a for a in result if "pre-commit" in a.path)
        assert "--stage pre-commit" in pre_commit.content

    def test_pre_push_has_correct_stage(self, tmp_path: Path) -> None:
        (tmp_path / ".git").mkdir()
        (tmp_path / ".git" / "hooks").mkdir()
        result = generate_git_hooks(tmp_path)
        pre_push = next(a for a in result if "pre-push" in a.path)
        assert "--stage pre-push" in pre_push.content


# ---------------------------------------------------------------------------
# G3: Tool Configs Tests
# ---------------------------------------------------------------------------


class TestGenerateToolConfigs:
    """generate_tool_configs function tests."""

    def test_returns_empty_list_when_no_rulesets(self, tmp_path: Path) -> None:
        result = generate_tool_configs(tmp_path, [])
        assert result == []

    def test_returns_empty_list_when_cache_missing(self, tmp_path: Path) -> None:
        result = generate_tool_configs(tmp_path, ["company-rules"])
        assert result == []

    def test_copies_files_from_ruleset(self, tmp_path: Path) -> None:
        # Create mock ruleset cache
        cache_dir = tmp_path / ".ac-guard" / "cache" / "company-rules" / "files"
        cache_dir.mkdir(parents=True)
        (cache_dir / ".clang-format").write_text("Format config", encoding="utf-8")

        result = generate_tool_configs(tmp_path, ["company-rules"])
        assert len(result) == 1
        assert result[0].path == ".clang-format"
        assert result[0].content == "Format config"

    def test_copies_from_multiple_rulesets(self, tmp_path: Path) -> None:
        # Create two ruleset caches
        cache1 = tmp_path / ".ac-guard" / "cache" / "ruleset-a" / "files"
        cache1.mkdir(parents=True)
        (cache1 / "config-a.yaml").write_text("a", encoding="utf-8")

        cache2 = tmp_path / ".ac-guard" / "cache" / "ruleset-b" / "files"
        cache2.mkdir(parents=True)
        (cache2 / "config-b.yaml").write_text("b", encoding="utf-8")

        result = generate_tool_configs(tmp_path, ["ruleset-a", "ruleset-b"])
        assert len(result) == 2
        paths = [a.path for a in result]
        assert "config-a.yaml" in paths
        assert "config-b.yaml" in paths

    def test_skips_missing_ruleset(self, tmp_path: Path) -> None:
        # Create only one ruleset cache
        cache = tmp_path / ".ac-guard" / "cache" / "existing" / "files"
        cache.mkdir(parents=True)
        (cache / "file.txt").write_text("content", encoding="utf-8")

        result = generate_tool_configs(tmp_path, ["existing", "missing"])
        assert len(result) == 1
        assert result[0].path == "file.txt"

    def test_skips_binary_files(self, tmp_path: Path) -> None:
        cache = tmp_path / ".ac-guard" / "cache" / "ruleset" / "files"
        cache.mkdir(parents=True)
        (cache / "text.txt").write_text("text", encoding="utf-8")
        # Write binary file
        (cache / "binary.bin").write_bytes(b"\x00\xff\xfe")

        result = generate_tool_configs(tmp_path, ["ruleset"])
        # Should only have text file
        assert len(result) == 1
        assert result[0].path == "text.txt"


class TestGenerateToolConfigsForce:
    """generate_tool_configs force/skip behavior tests."""

    def test_skips_existing_file_by_default(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Existing user file should be skipped with warning when force=False."""
        cache = tmp_path / ".ac-guard" / "cache" / "rules" / "files"
        cache.mkdir(parents=True)
        (cache / ".editorconfig").write_text("ruleset content", encoding="utf-8")

        # User already has this file
        (tmp_path / ".editorconfig").write_text("user content", encoding="utf-8")

        result = generate_tool_configs(tmp_path, ["rules"], force=False)
        assert len(result) == 0

        captured = capsys.readouterr()
        assert ".editorconfig" in captured.out
        assert "skip" in captured.out.lower() or "exists" in captured.out.lower()

    def test_overwrites_existing_file_when_forced(self, tmp_path: Path) -> None:
        """Existing file should be included when force=True."""
        cache = tmp_path / ".ac-guard" / "cache" / "rules" / "files"
        cache.mkdir(parents=True)
        (cache / ".editorconfig").write_text("ruleset content", encoding="utf-8")

        (tmp_path / ".editorconfig").write_text("user content", encoding="utf-8")

        result = generate_tool_configs(tmp_path, ["rules"], force=True)
        assert len(result) == 1
        assert result[0].content == "ruleset content"

    def test_copies_new_file_regardless_of_force(self, tmp_path: Path) -> None:
        """New files should always be copied, even with force=False."""
        cache = tmp_path / ".ac-guard" / "cache" / "rules" / "files"
        cache.mkdir(parents=True)
        (cache / "new-config.yml").write_text("new", encoding="utf-8")

        result = generate_tool_configs(tmp_path, ["rules"], force=False)
        assert len(result) == 1
        assert result[0].path == "new-config.yml"

    def test_mixed_existing_and_new(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Only existing files should be skipped; new files still copied."""
        cache = tmp_path / ".ac-guard" / "cache" / "rules" / "files"
        cache.mkdir(parents=True)
        (cache / "existing.cfg").write_text("from ruleset", encoding="utf-8")
        (cache / "new.cfg").write_text("new config", encoding="utf-8")

        (tmp_path / "existing.cfg").write_text("user version", encoding="utf-8")

        result = generate_tool_configs(tmp_path, ["rules"], force=False)
        assert len(result) == 1
        assert result[0].path == "new.cfg"


class TestGenerateCheckScripts:
    """generate_check_scripts function tests."""

    def test_returns_empty_list_when_no_rulesets(self, tmp_path: Path) -> None:
        from ac_guard.generator.core import generate_check_scripts

        result = generate_check_scripts(tmp_path, [])
        assert result == []

    def test_returns_empty_list_when_cache_missing(self, tmp_path: Path) -> None:
        from ac_guard.generator.core import generate_check_scripts

        result = generate_check_scripts(tmp_path, ["company-rules"])
        assert result == []

    def test_copies_scripts_to_ac_guard_checks(self, tmp_path: Path) -> None:
        from ac_guard.generator.core import generate_check_scripts

        cache = tmp_path / ".ac-guard" / "cache" / "rules" / "checks"
        cache.mkdir(parents=True)
        (cache / "encoding_check.py").write_text("# check", encoding="utf-8")

        result = generate_check_scripts(tmp_path, ["rules"])
        assert len(result) == 1
        assert result[0].path == ".ac-guard/checks/encoding_check.py"
        assert result[0].content == "# check"

    def test_copies_from_multiple_rulesets(self, tmp_path: Path) -> None:
        from ac_guard.generator.core import generate_check_scripts

        cache1 = tmp_path / ".ac-guard" / "cache" / "a" / "checks"
        cache1.mkdir(parents=True)
        (cache1 / "check_a.py").write_text("a", encoding="utf-8")

        cache2 = tmp_path / ".ac-guard" / "cache" / "b" / "checks"
        cache2.mkdir(parents=True)
        (cache2 / "check_b.py").write_text("b", encoding="utf-8")

        result = generate_check_scripts(tmp_path, ["a", "b"])
        assert len(result) == 2
        paths = [r.path for r in result]
        assert ".ac-guard/checks/check_a.py" in paths
        assert ".ac-guard/checks/check_b.py" in paths

    def test_skips_binary_files(self, tmp_path: Path) -> None:
        from ac_guard.generator.core import generate_check_scripts

        cache = tmp_path / ".ac-guard" / "cache" / "rules" / "checks"
        cache.mkdir(parents=True)
        (cache / "check.py").write_text("# ok", encoding="utf-8")
        (cache / "binary.bin").write_bytes(b"\x00\xff\xfe")

        result = generate_check_scripts(tmp_path, ["rules"])
        assert len(result) == 1
        assert result[0].path == ".ac-guard/checks/check.py"

    def test_skips_missing_checks_dir(self, tmp_path: Path) -> None:
        from ac_guard.generator.core import generate_check_scripts

        # Ruleset exists in cache but has no checks/ dir
        cache = tmp_path / ".ac-guard" / "cache" / "rules"
        cache.mkdir(parents=True)
        (cache / "guard.yaml").write_text("version: 1", encoding="utf-8")

        result = generate_check_scripts(tmp_path, ["rules"])
        assert result == []


# ---------------------------------------------------------------------------
# G4: Pre-commit Config Tests
# ---------------------------------------------------------------------------


class TestGeneratePrecommitConfig:
    """generate_precommit_config function tests."""

    def test_returns_file_spec(self) -> None:
        code = CodeConfig()
        languages = {"python": LanguageTools(format="black", lint="ruff")}
        result = generate_precommit_config(code, languages)
        assert isinstance(result, FileSpec)
        assert result.path == ".pre-commit-config.yaml"

    def test_includes_repo_local(self) -> None:
        code = CodeConfig(pre_commit=StageBucket(format=True))
        languages = {"python": LanguageTools(format="black", lint="ruff")}
        result = generate_precommit_config(code, languages)
        assert "repo: local" in result.content

    def test_includes_format_hooks_when_enabled(self) -> None:
        code = CodeConfig(pre_commit=StageBucket(format=True))
        languages = {"python": LanguageTools(format="black", lint="ruff")}
        result = generate_precommit_config(code, languages)
        assert "format-python" in result.content
        assert "black" in result.content

    def test_includes_lint_hooks_when_enabled(self) -> None:
        code = CodeConfig(pre_push=StageBucket(lint=True))
        languages = {"python": LanguageTools(format="black", lint="ruff")}
        result = generate_precommit_config(code, languages)
        assert "lint-python" in result.content
        assert "ruff" in result.content

    def test_omits_format_when_disabled(self) -> None:
        code = CodeConfig(pre_commit=StageBucket(format=False))
        languages = {"python": LanguageTools(format="black", lint="ruff")}
        result = generate_precommit_config(code, languages)
        assert "format-python" not in result.content

    def test_includes_custom_checks(self) -> None:
        code = CodeConfig(
            pre_commit=StageBucket(
                checks={
                    "test": CheckItem(command="pytest", pass_filenames=False),
                }
            ),
        )
        languages = {}
        result = generate_precommit_config(code, languages)
        assert "custom-test" in result.content
        assert "pytest" in result.content

    def test_includes_language_types(self) -> None:
        code = CodeConfig(pre_commit=StageBucket(format=True))
        languages = {"python": LanguageTools(format="black", lint="ruff")}
        result = generate_precommit_config(code, languages)
        # Schema v2 emits JSON-serialized types (via ``tojson`` filter)
        assert '"python"' in result.content

    def test_handles_multiple_languages(self) -> None:
        code = CodeConfig(
            pre_commit=StageBucket(format=True), pre_push=StageBucket(lint=True)
        )
        languages = {
            "python": LanguageTools(format="black", lint="ruff"),
            "typescript": LanguageTools(format="prettier", lint="eslint"),
        }
        result = generate_precommit_config(code, languages)
        assert "format-python" in result.content
        assert "format-typescript" in result.content
        assert "lint-python" in result.content
        assert "lint-typescript" in result.content


class TestPrecommitArtifactLifecycle:
    """Schema v2: `.pre-commit-config.yaml` is a pure generated artifact.

    D4 in issue #123 dropped the managed-block contract for this file —
    the whole file comes from guard.yaml on every install. Tests below
    verify the overwrite semantics instead of the old block-preservation
    behaviour.
    """

    @staticmethod
    def _write_precommit(
        tmp_path: Path, *, format_on: bool = True, lint_on: bool = True
    ) -> str:
        code = CodeConfig(
            pre_commit=StageBucket(format=format_on),
            pre_push=StageBucket(lint=lint_on),
        )
        languages = {"python": LanguageTools(format="black", lint="ruff")}
        spec = generate_precommit_config(code, languages)
        write_artifacts(tmp_path, [spec])
        return (tmp_path / ".pre-commit-config.yaml").read_text(encoding="utf-8")

    def test_no_managed_block_markers_emitted(self) -> None:
        code = CodeConfig(pre_commit=StageBucket(format=True))
        languages = {"python": LanguageTools(format="black", lint="ruff")}
        result = generate_precommit_config(code, languages)
        # D4: template no longer embeds AI-GUARD markers.
        assert MARKER_BEGIN_HASH not in result.content
        assert MARKER_END_HASH not in result.content
        assert MARKER_BEGIN not in result.content
        assert MARKER_END not in result.content

    def test_header_warns_against_hand_edit(self) -> None:
        code = CodeConfig(pre_commit=StageBucket(format=True))
        result = generate_precommit_config(
            code, {"python": LanguageTools(format="black", lint="ruff")}
        )
        assert "Generated by ac-guard install" in result.content
        assert "DO NOT EDIT" in result.content

    def test_overwrite_drops_user_edits(self, tmp_path: Path) -> None:
        """Any hand edits to .pre-commit-config.yaml are lost on install.

        This is intentional under schema v2 (D4) — guard.yaml is the
        sole source of truth. Use `ac-guard import` (#124) to migrate
        existing hand-written configs into guard.yaml.
        """
        self._write_precommit(tmp_path)
        cfg = tmp_path / ".pre-commit-config.yaml"
        cfg.write_text("# hand edit\nrepos: []\n", encoding="utf-8")
        self._write_precommit(tmp_path)
        content = cfg.read_text(encoding="utf-8")
        assert "hand edit" not in content
        assert "Generated by ac-guard install" in content

    def test_repeated_install_produces_same_content(self, tmp_path: Path) -> None:
        """Byte-stable regeneration so commits stay noise-free."""
        first = self._write_precommit(tmp_path)
        second = self._write_precommit(tmp_path)
        assert first == second
