"""Tests for ac_guard.domain.models — cross-module data contracts and
managed-block protocol helpers.
"""

from __future__ import annotations

from ac_guard.domain import (
    MARKER_BEGIN,
    MARKER_BEGIN_HASH,
    MARKER_END,
    MARKER_END_HASH,
    FileSpec,
    markers_for,
    wrap_with_markers,
)

# ---------------------------------------------------------------------------
# A. Managed-block marker constants
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


# ---------------------------------------------------------------------------
# B. markers_for(path)
# ---------------------------------------------------------------------------


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
        assert markers_for("README") == (MARKER_BEGIN, MARKER_END)
        assert markers_for("policy.json") == (MARKER_BEGIN, MARKER_END)

    def test_case_insensitive_extension_match(self) -> None:
        assert markers_for("Makefile.YAML") == (MARKER_BEGIN_HASH, MARKER_END_HASH)


# ---------------------------------------------------------------------------
# C. wrap_with_markers(path, content)
# ---------------------------------------------------------------------------


class TestWrapWithMarkers:
    def test_output_structure_html(self) -> None:
        result = wrap_with_markers("RULES.md", "line1")
        assert result.startswith(MARKER_BEGIN)
        assert result.endswith(MARKER_END + "\n")
        assert "line1" in result

    def test_output_structure_hash(self) -> None:
        result = wrap_with_markers("config.yaml", "body")
        assert result.startswith(MARKER_BEGIN_HASH)
        assert result.endswith(MARKER_END_HASH + "\n")
        assert MARKER_BEGIN not in result  # HTML markers must not leak

    def test_empty_content(self) -> None:
        result = wrap_with_markers("RULES.md", "")
        assert MARKER_BEGIN in result
        assert MARKER_END in result

    def test_exact_shape(self) -> None:
        result = wrap_with_markers("RULES.md", "X")
        assert result == f"{MARKER_BEGIN}\nX\n{MARKER_END}\n"


# ---------------------------------------------------------------------------
# D. FileSpec
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


class TestFileSpecFromBody:
    """FileSpec.from_body is the named constructor that wraps body in markers."""

    def test_builds_with_html_markers_for_markdown(self) -> None:
        spec = FileSpec.from_body("CLAUDE.md", "rules body")
        assert spec.path == "CLAUDE.md"
        assert spec.content == f"{MARKER_BEGIN}\nrules body\n{MARKER_END}\n"
        assert spec.executable is False

    def test_builds_with_hash_markers_for_yaml(self) -> None:
        spec = FileSpec.from_body(".pre-commit-config.yaml", "repos:\n  - id: foo")
        expected = f"{MARKER_BEGIN_HASH}\nrepos:\n  - id: foo\n{MARKER_END_HASH}\n"
        assert spec.content == expected

    def test_executable_always_false(self) -> None:
        """The wrap path is never used for executable hook scripts."""
        spec = FileSpec.from_body("RULES.md", "body")
        assert spec.executable is False


# ---------------------------------------------------------------------------
# E. Module exports
# ---------------------------------------------------------------------------


class TestModuleExports:
    def test_domain_package_exports(self) -> None:
        from ac_guard.domain import (  # noqa: F401
            MARKER_BEGIN,
            MARKER_BEGIN_HASH,
            MARKER_END,
            MARKER_END_HASH,
            CheckResult,
            FileSpec,
            StageOutcome,
            Violation,
            markers_for,
            wrap_with_markers,
        )

    def test_all_list(self) -> None:
        import ac_guard.domain as domain

        assert set(domain.__all__) == {
            "MARKER_BEGIN",
            "MARKER_BEGIN_HASH",
            "MARKER_END",
            "MARKER_END_HASH",
            "CheckResult",
            "FileSpec",
            "StageOutcome",
            "Violation",
            "markers_for",
            "wrap_with_markers",
        }
