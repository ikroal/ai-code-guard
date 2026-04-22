"""Tests for ac_guard.domain.managed_block — Domain Service covering
the full CRUD lifecycle of an ac-guard managed block.
"""

from __future__ import annotations

import pytest

from ac_guard.domain import FileSpec, managed_block

# Literal marker strings mirror the (private) module constants. Tests
# reference these directly so a regression in the marker-style dispatcher
# fails loudly at the assertion rather than being silently swallowed by
# round-tripping through the same dispatcher.
_HTML_BEGIN = "<!-- AI-GUARD:BEGIN -->"
_HTML_END = "<!-- AI-GUARD:END -->"
_HASH_BEGIN = "# AI-GUARD:BEGIN"
_HASH_END = "# AI-GUARD:END"


# ---------------------------------------------------------------------------
# A. CREATE — wrap(body, *, path)
# ---------------------------------------------------------------------------


class TestWrap:
    """CREATE: build managed content from a body."""

    def test_html_markers_for_markdown(self) -> None:
        result = managed_block.wrap("body text", path="CLAUDE.md")
        assert result == f"{_HTML_BEGIN}\nbody text\n{_HTML_END}\n"

    def test_html_markers_for_mdc(self) -> None:
        result = managed_block.wrap("body", path="rules/behavior.mdc")
        assert result.startswith(_HTML_BEGIN)
        assert result.endswith(_HTML_END + "\n")

    def test_hash_markers_for_yaml(self) -> None:
        result = managed_block.wrap("repos: []", path="config.yaml")
        assert result == f"{_HASH_BEGIN}\nrepos: []\n{_HASH_END}\n"

    def test_hash_markers_for_yml(self) -> None:
        result = managed_block.wrap("x", path="a.yml")
        assert result.startswith(_HASH_BEGIN)

    def test_hash_markers_for_toml(self) -> None:
        result = managed_block.wrap("x", path="pyproject.toml")
        assert result.startswith(_HASH_BEGIN)

    def test_hash_markers_for_sh(self) -> None:
        result = managed_block.wrap("x", path="scripts/install.sh")
        assert result.startswith(_HASH_BEGIN)

    def test_hash_markers_for_py(self) -> None:
        result = managed_block.wrap("x", path="a.py")
        assert result.startswith(_HASH_BEGIN)

    def test_unknown_extension_falls_back_to_html(self) -> None:
        result = managed_block.wrap("x", path="README")
        assert result.startswith(_HTML_BEGIN)

    def test_case_insensitive_extension(self) -> None:
        result = managed_block.wrap("x", path="Makefile.YAML")
        assert result.startswith(_HASH_BEGIN)

    def test_empty_body(self) -> None:
        result = managed_block.wrap("", path="x.md")
        assert result == f"{_HTML_BEGIN}\n\n{_HTML_END}\n"

    def test_multiline_body_preserved(self) -> None:
        body = "line 1\nline 2\nline 3"
        result = managed_block.wrap(body, path="x.md")
        assert body in result


# ---------------------------------------------------------------------------
# B. READ (presence) — has(content, *, path)
# ---------------------------------------------------------------------------


class TestHas:
    """READ.presence: is there a managed block in this content?"""

    def test_true_when_both_markers_present(self) -> None:
        content = managed_block.wrap("body", path="x.md")
        assert managed_block.has(content, path="x.md") is True

    def test_false_when_no_markers(self) -> None:
        assert managed_block.has("plain user text", path="x.md") is False

    def test_false_when_only_begin(self) -> None:
        assert managed_block.has(f"{_HTML_BEGIN}\nbody\n", path="x.md") is False

    def test_false_when_only_end(self) -> None:
        assert managed_block.has(f"body\n{_HTML_END}\n", path="x.md") is False

    def test_path_extension_changes_marker_style(self) -> None:
        # An HTML-marked block in a YAML file is NOT a valid managed block.
        html_block = managed_block.wrap("x", path="x.md")
        assert managed_block.has(html_block, path="x.yaml") is False

    def test_hash_block_in_yaml(self) -> None:
        yaml_block = managed_block.wrap("x", path="config.yaml")
        assert managed_block.has(yaml_block, path="config.yaml") is True

    def test_empty_content(self) -> None:
        assert managed_block.has("", path="x.md") is False


# ---------------------------------------------------------------------------
# C. READ (body) — read(content, *, path)
# ---------------------------------------------------------------------------


class TestRead:
    """READ.value: extract the body from a managed block."""

    def test_reads_body_html(self) -> None:
        content = managed_block.wrap("hello world", path="x.md")
        assert managed_block.read(content, path="x.md") == "hello world"

    def test_reads_body_hash(self) -> None:
        content = managed_block.wrap("repos: []", path="a.yaml")
        assert managed_block.read(content, path="a.yaml") == "repos: []"

    def test_none_when_missing_markers(self) -> None:
        assert managed_block.read("plain text", path="x.md") is None

    def test_none_when_only_begin(self) -> None:
        assert managed_block.read(f"{_HTML_BEGIN}\nx\n", path="x.md") is None

    def test_none_when_malformed_order(self) -> None:
        # END appears before BEGIN → malformed
        content = f"{_HTML_END}\nfoo\n{_HTML_BEGIN}\n"
        assert managed_block.read(content, path="x.md") is None

    def test_preserves_surrounding_user_content_in_read(self) -> None:
        # User lines above/below markers must not bleed into the extracted body.
        content = f"User prefix\n{_HTML_BEGIN}\nmanaged body\n{_HTML_END}\nUser suffix"
        assert managed_block.read(content, path="x.md") == "managed body"

    def test_multiline_body_preserved(self) -> None:
        body = "line1\nline2\nline3"
        content = managed_block.wrap(body, path="x.md")
        assert managed_block.read(content, path="x.md") == body

    def test_empty_body_returns_empty_string(self) -> None:
        content = f"{_HTML_BEGIN}\n\n{_HTML_END}\n"
        assert managed_block.read(content, path="x.md") == ""


# ---------------------------------------------------------------------------
# D. UPDATE — replace(content, new_body, *, path)
# ---------------------------------------------------------------------------


class TestReplace:
    """UPDATE: swap the managed-block body, or append a new block if absent."""

    def test_replaces_body_between_markers(self) -> None:
        existing = f"Header\n{_HTML_BEGIN}\nOld\n{_HTML_END}\nFooter"
        result = managed_block.replace(existing, "New", path="x.md")
        assert "Header" in result
        assert "Footer" in result
        assert "Old" not in result
        assert "New" in result

    def test_preserves_content_before_markers(self) -> None:
        existing = f"Keep this\n{_HTML_BEGIN}\nReplace\n{_HTML_END}\n"
        result = managed_block.replace(existing, "New", path="x.md")
        assert "Keep this" in result

    def test_preserves_content_after_markers(self) -> None:
        existing = f"{_HTML_BEGIN}\nReplace\n{_HTML_END}\nKeep this too\n"
        result = managed_block.replace(existing, "New", path="x.md")
        assert "Keep this too" in result

    def test_appends_wrapped_block_when_markers_missing(self) -> None:
        existing = "Existing without markers"
        result = managed_block.replace(existing, "New managed", path="x.md")
        assert "Existing without markers" in result
        assert _HTML_BEGIN in result
        assert _HTML_END in result
        assert "New managed" in result

    def test_handles_empty_existing(self) -> None:
        result = managed_block.replace("", "New", path="x.md")
        assert _HTML_BEGIN in result
        assert "New" in result
        assert _HTML_END in result

    def test_handles_multiline_new_body(self) -> None:
        existing = f"{_HTML_BEGIN}\nold_one\nold_two\n{_HTML_END}\n"
        result = managed_block.replace(existing, "X\nY\nZ", path="x.md")
        assert "X" in result
        assert "Y" in result
        assert "Z" in result
        assert "old_one" not in result
        assert "old_two" not in result

    def test_hash_marker_style_for_yaml(self) -> None:
        existing = f"repos:\n{_HASH_BEGIN}\nold\n{_HASH_END}\n"
        result = managed_block.replace(existing, "new", path="config.yaml")
        assert _HASH_BEGIN in result
        assert _HASH_END in result
        assert "new" in result
        assert "old" not in result

    def test_round_trip_replace_preserves_user_content(self) -> None:
        """Invariant: content outside managed block survives repeated replace."""
        existing = f"User header\n{_HTML_BEGIN}\nv1\n{_HTML_END}\nUser footer"
        round1 = managed_block.replace(existing, "v2", path="x.md")
        round2 = managed_block.replace(round1, "v3", path="x.md")
        assert "User header" in round2
        assert "User footer" in round2
        assert "v1" not in round2
        assert "v2" not in round2
        assert "v3" in round2


# ---------------------------------------------------------------------------
# E. DELETE — remove(content, *, path)
# ---------------------------------------------------------------------------


class TestRemove:
    """DELETE: strip the managed block, preserving surrounding content."""

    def test_removes_block_preserving_user_content(self) -> None:
        content = f"User header\n{_HTML_BEGIN}\nmanaged\n{_HTML_END}\nUser footer"
        result = managed_block.remove(content, path="x.md")
        assert _HTML_BEGIN not in result
        assert _HTML_END not in result
        assert "managed" not in result
        assert "User header" in result
        assert "User footer" in result

    def test_returns_content_unchanged_when_no_block(self) -> None:
        content = "User content only"
        assert managed_block.remove(content, path="x.md") == content

    def test_empty_content(self) -> None:
        assert managed_block.remove("", path="x.md") == ""

    def test_only_block_returns_empty(self) -> None:
        content = managed_block.wrap("managed body", path="x.md")
        result = managed_block.remove(content, path="x.md")
        assert result == ""

    def test_block_at_start_preserves_suffix(self) -> None:
        content = managed_block.wrap("managed", path="x.md") + "User suffix"
        result = managed_block.remove(content, path="x.md")
        assert result == "User suffix"

    def test_hash_style_remove(self) -> None:
        content = f"repos:\n{_HASH_BEGIN}\nmanaged\n{_HASH_END}\n  - user-added\n"
        result = managed_block.remove(content, path="config.yaml")
        assert "managed" not in result
        assert _HASH_BEGIN not in result
        assert "repos:" in result
        assert "user-added" in result


# ---------------------------------------------------------------------------
# F. FACTORY — file_spec(path, body)
# ---------------------------------------------------------------------------


class TestFileSpec:
    """FACTORY: build a FileSpec whose content is a wrapped managed block."""

    def test_returns_file_spec_instance(self) -> None:
        spec = managed_block.file_spec("CLAUDE.md", "body")
        assert isinstance(spec, FileSpec)

    def test_path_is_preserved(self) -> None:
        spec = managed_block.file_spec("path/to/file.md", "body")
        assert spec.path == "path/to/file.md"

    def test_content_is_wrapped(self) -> None:
        spec = managed_block.file_spec("CLAUDE.md", "body text")
        assert spec.content == f"{_HTML_BEGIN}\nbody text\n{_HTML_END}\n"

    def test_hash_style_inferred_from_yaml_path(self) -> None:
        spec = managed_block.file_spec("config.yaml", "x")
        assert spec.content.startswith(_HASH_BEGIN)

    def test_executable_defaults_false(self) -> None:
        spec = managed_block.file_spec("x.md", "body")
        assert spec.executable is False


# ---------------------------------------------------------------------------
# G. Closed-loop invariants
# ---------------------------------------------------------------------------


class TestClosedLoop:
    """Invariants that hold across op combinations."""

    @pytest.mark.parametrize(
        "path",
        [
            "CLAUDE.md",
            "rules.mdc",
            "config.yaml",
            "x.yml",
            "pyproject.toml",
            "a.sh",
            "a.py",
        ],
    )
    def test_wrap_then_read_recovers_body(self, path: str) -> None:
        body = "some content"
        assert (
            managed_block.read(managed_block.wrap(body, path=path), path=path) == body
        )

    @pytest.mark.parametrize("path", ["x.md", "config.yaml"])
    def test_wrap_then_has_is_true(self, path: str) -> None:
        assert managed_block.has(managed_block.wrap("b", path=path), path=path) is True

    def test_replace_of_fresh_content_is_append(self) -> None:
        a = managed_block.replace("", "body", path="x.md")
        b = managed_block.wrap("body", path="x.md")
        assert a == b

    def test_remove_after_wrap_returns_empty(self) -> None:
        assert (
            managed_block.remove(managed_block.wrap("x", path="a.md"), path="a.md")
            == ""
        )

    def test_file_spec_content_equals_wrap(self) -> None:
        spec = managed_block.file_spec("x.md", "body")
        assert spec.content == managed_block.wrap("body", path="x.md")


# ---------------------------------------------------------------------------
# H. Module exports
# ---------------------------------------------------------------------------


class TestModuleExports:
    def test_public_api(self) -> None:
        assert set(managed_block.__all__) == {
            "file_spec",
            "has",
            "read",
            "remove",
            "replace",
            "wrap",
        }

    def test_markers_are_private(self) -> None:
        """Raw marker constants and dispatcher must not leak as public names."""
        for name in (
            "MARKER_BEGIN",
            "MARKER_END",
            "MARKER_BEGIN_HASH",
            "MARKER_END_HASH",
            "markers_for",
            "HASH_COMMENT_EXTS",
        ):
            assert name not in managed_block.__all__
            # Private names exist with `_` prefix for internal use.
            assert not hasattr(managed_block, name), (
                f"Unexpected public name leaked: {name}"
            )
