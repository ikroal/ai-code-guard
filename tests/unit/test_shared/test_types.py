"""Tests for ac_guard.shared.types — Shared types module."""

from __future__ import annotations

from ac_guard.shared.types import (
    MARKER_BEGIN,
    MARKER_BEGIN_HASH,
    MARKER_END,
    MARKER_END_HASH,
    FileSpec,
    markers_for,
    wrap_with_managed_block,
)

# ---------------------------------------------------------------------------
# A. Managed Block Markers
# ---------------------------------------------------------------------------


class TestManagedBlockMarkers:
    def test_marker_begin_value(self) -> None:
        assert MARKER_BEGIN == "<!-- AI-GUARD:BEGIN -->"

    def test_marker_end_value(self) -> None:
        assert MARKER_END == "<!-- AI-GUARD:END -->"

    def test_hash_marker_values(self) -> None:
        assert MARKER_BEGIN_HASH == "# AI-GUARD:BEGIN"
        assert MARKER_END_HASH == "# AI-GUARD:END"

    def test_markers_are_strings(self) -> None:
        assert isinstance(MARKER_BEGIN, str)
        assert isinstance(MARKER_END, str)
        assert isinstance(MARKER_BEGIN_HASH, str)
        assert isinstance(MARKER_END_HASH, str)


class TestMarkersFor:
    """markers_for(path) picks hash-style for hash-comment syntaxes."""

    def test_yaml_gets_hash_markers(self) -> None:
        assert markers_for(".pre-commit-config.yaml") == (
            MARKER_BEGIN_HASH,
            MARKER_END_HASH,
        )
        assert markers_for("config.yml") == (MARKER_BEGIN_HASH, MARKER_END_HASH)

    def test_toml_gets_hash_markers(self) -> None:
        assert markers_for("pyproject.toml") == (MARKER_BEGIN_HASH, MARKER_END_HASH)

    def test_python_and_shell_get_hash_markers(self) -> None:
        assert markers_for("scripts/install.sh") == (
            MARKER_BEGIN_HASH,
            MARKER_END_HASH,
        )
        assert markers_for("src/app/main.py") == (MARKER_BEGIN_HASH, MARKER_END_HASH)

    def test_markdown_gets_html_markers(self) -> None:
        assert markers_for("CLAUDE.md") == (MARKER_BEGIN, MARKER_END)
        assert markers_for("rules/behavior.mdc") == (MARKER_BEGIN, MARKER_END)

    def test_unknown_extension_falls_back_to_html(self) -> None:
        # Default protects old callers that couldn't specify a path.
        assert markers_for("README") == (MARKER_BEGIN, MARKER_END)
        assert markers_for("policy.json") == (MARKER_BEGIN, MARKER_END)

    def test_case_insensitive_extension_match(self) -> None:
        assert markers_for("Makefile.YAML") == (MARKER_BEGIN_HASH, MARKER_END_HASH)


class TestWrapWithManagedBlock:
    def test_wraps_content(self) -> None:
        content = "test content"
        result = wrap_with_managed_block(content)
        assert MARKER_BEGIN in result
        assert MARKER_END in result
        assert "test content" in result

    def test_output_structure(self) -> None:
        content = "line1"
        result = wrap_with_managed_block(content)
        # Should have: BEGIN, newline, content, newline, END, newline
        assert result.startswith(MARKER_BEGIN)
        assert result.endswith(MARKER_END + "\n")

    def test_empty_content(self) -> None:
        result = wrap_with_managed_block("")
        assert MARKER_BEGIN in result
        assert MARKER_END in result

    def test_path_selects_hash_markers(self) -> None:
        """Passing a hash-style path produces hash-style markers."""
        result = wrap_with_managed_block("body", path="config.yaml")
        assert result.startswith(MARKER_BEGIN_HASH)
        assert result.endswith(MARKER_END_HASH + "\n")
        assert MARKER_BEGIN not in result  # no HTML markers leaked

    def test_path_selects_html_markers_for_markdown(self) -> None:
        result = wrap_with_managed_block("body", path="RULES.md")
        assert result.startswith(MARKER_BEGIN)
        assert result.endswith(MARKER_END + "\n")
        assert MARKER_BEGIN_HASH not in result


# ---------------------------------------------------------------------------
# B. FileSpec
# ---------------------------------------------------------------------------


class TestFileSpec:
    def test_basic_construction(self) -> None:
        spec = FileSpec(path="test.txt", content="hello")
        assert spec.path == "test.txt"
        assert spec.content == "hello"

    def test_executable_flag(self) -> None:
        spec = FileSpec(path="script.sh", content="#!/bin/bash", executable=True)
        assert spec.executable is True

    def test_executable_default_false(self) -> None:
        spec = FileSpec(path="file.py", content="code")
        assert spec.executable is False

    def test_all_fields(self) -> None:
        spec = FileSpec(
            path=".claude/hooks/interceptor.py",
            content="#!/usr/bin/env python",
            executable=True,
        )
        assert spec.path == ".claude/hooks/interceptor.py"
        assert spec.content == "#!/usr/bin/env python"
        assert spec.executable is True


# ---------------------------------------------------------------------------
# C. Module exports
# ---------------------------------------------------------------------------


class TestModuleExports:
    def test_types_exports(self) -> None:
        from ac_guard.shared.types import (  # noqa: F401
            MARKER_BEGIN,
            MARKER_END,
            FileSpec,
            wrap_with_managed_block,
        )

    def test_all_list(self) -> None:
        import ac_guard.shared.types as types

        assert set(types.__all__) == {
            "FileSpec",
            "MARKER_BEGIN",
            "MARKER_BEGIN_HASH",
            "MARKER_END",
            "MARKER_END_HASH",
            "markers_for",
            "wrap_with_managed_block",
        }

    def test_shared_package_exports(self) -> None:
        from ac_guard.shared import (  # noqa: F401
            MARKER_BEGIN,
            MARKER_END,
            FileSpec,
            wrap_with_managed_block,
        )
