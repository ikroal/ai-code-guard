"""Tests for ai_guard.shared.types — Shared types module."""

from __future__ import annotations

from ai_guard.shared.types import (
    MARKER_BEGIN,
    MARKER_END,
    FileSpec,
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

    def test_markers_are_strings(self) -> None:
        assert isinstance(MARKER_BEGIN, str)
        assert isinstance(MARKER_END, str)


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
        from ai_guard.shared.types import (  # noqa: F401
            MARKER_BEGIN,
            MARKER_END,
            FileSpec,
            wrap_with_managed_block,
        )

    def test_all_list(self) -> None:
        import ai_guard.shared.types as types

        assert set(types.__all__) == {
            "FileSpec",
            "MARKER_BEGIN",
            "MARKER_END",
            "wrap_with_managed_block",
        }

    def test_shared_package_exports(self) -> None:
        from ai_guard.shared import (  # noqa: F401
            MARKER_BEGIN,
            MARKER_END,
            FileSpec,
            wrap_with_managed_block,
        )
