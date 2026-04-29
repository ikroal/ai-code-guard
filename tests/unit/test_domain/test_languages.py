"""Tests for ac_guard.domain.languages — Domain Service for the
ac-guard language registry (path → language and the underlying
extension table).
"""

from __future__ import annotations

import pytest

from ac_guard.domain import languages

# Snapshot of the registered languages. The data table is a domain
# contract: any change must come with a deliberate code review,
# because format/lint shortcut emission and doctor's language
# coverage diagnostic both depend on this set.
_EXPECTED_LANGUAGES = frozenset(
    {
        "python",
        "javascript",
        "typescript",
        "go",
        "rust",
        "java",
        "c",
        "cpp",
    }
)


# ---------------------------------------------------------------------------
# A. TYPE_EXTENSIONS shape and contents
# ---------------------------------------------------------------------------


class TestTypeExtensionsShape:
    """The registry is a dict[str, frozenset[str]] keyed on language name."""

    def test_keys_match_expected_languages(self) -> None:
        assert frozenset(languages.TYPE_EXTENSIONS) == _EXPECTED_LANGUAGES

    def test_values_are_frozenset_of_str(self) -> None:
        for lang, exts in languages.TYPE_EXTENSIONS.items():
            assert isinstance(exts, frozenset), (
                f"{lang}: expected frozenset, got {type(exts).__name__}"
            )
            assert exts, f"{lang}: extension set is empty"
            for ext in exts:
                assert isinstance(ext, str)
                assert ext.startswith("."), f"{lang}: {ext!r} missing leading dot"

    def test_extensions_are_lowercase(self) -> None:
        """detect_language lowercases input; the table must be lowercase too."""
        for lang, exts in languages.TYPE_EXTENSIONS.items():
            for ext in exts:
                assert ext == ext.lower(), f"{lang}: {ext!r} not lowercase"

    def test_no_extension_collisions_across_languages(self) -> None:
        """Each extension belongs to exactly one language."""
        seen: dict[str, str] = {}
        for lang, exts in languages.TYPE_EXTENSIONS.items():
            for ext in exts:
                if ext in seen:
                    pytest.fail(
                        f"{ext!r} registered for both {seen[ext]!r} and {lang!r}"
                    )
                seen[ext] = lang


# ---------------------------------------------------------------------------
# B. detect_language — path → language
# ---------------------------------------------------------------------------


class TestDetectLanguageRegistered:
    """Every registered language is detectable via at least one extension."""

    @pytest.mark.parametrize(
        ("path", "expected"),
        [
            ("foo.py", "python"),
            ("foo.pyi", "python"),
            ("foo.js", "javascript"),
            ("foo.jsx", "javascript"),
            ("foo.mjs", "javascript"),
            ("foo.ts", "typescript"),
            ("foo.tsx", "typescript"),
            ("foo.mts", "typescript"),
            ("foo.go", "go"),
            ("foo.rs", "rust"),
            ("foo.java", "java"),
            ("foo.c", "c"),
            ("foo.h", "c"),
            ("foo.cpp", "cpp"),
            ("foo.cc", "cpp"),
            ("foo.cxx", "cpp"),
            ("foo.hpp", "cpp"),
            ("foo.hh", "cpp"),
        ],
    )
    def test_known_extension_resolves(self, path: str, expected: str) -> None:
        assert languages.detect_language(path) == expected


class TestDetectLanguageEdgeCases:
    """detect_language handles real-world path shapes."""

    def test_uppercase_extension_matched(self) -> None:
        """``.PY``-style extensions still map to python (case-insensitive)."""
        assert languages.detect_language("MAIN.PY") == "python"

    def test_mixed_case_extension_matched(self) -> None:
        assert languages.detect_language("Main.Java") == "java"

    def test_path_prefix_ignored(self) -> None:
        """Directory components don't affect detection."""
        assert languages.detect_language("a/b/c/d.py") == "python"
        assert languages.detect_language("/abs/path/to/script.go") == "go"

    def test_unknown_extension_returns_none(self) -> None:
        assert languages.detect_language("README.md") is None
        assert languages.detect_language("Cargo.toml") is None
        assert languages.detect_language("config.yaml") is None

    def test_no_extension_returns_none(self) -> None:
        assert languages.detect_language("Makefile") is None
        assert languages.detect_language("/etc/hosts") is None
        assert languages.detect_language("") is None

    def test_dotfile_with_known_extension_matches(self) -> None:
        """A dotfile-like path whose tail matches an extension still resolves."""
        # Pathological but consistent: detect_language is suffix-based.
        assert languages.detect_language(".py") == "python"

    def test_extension_must_be_at_end(self) -> None:
        """Mid-path occurrences of extension-like substrings don't match."""
        # ".py" appears mid-path but the file ext is .txt → unknown.
        assert languages.detect_language("a.py.txt") is None


# ---------------------------------------------------------------------------
# C. Module surface
# ---------------------------------------------------------------------------


class TestPublicSurface:
    """The module's public contract is exactly TYPE_EXTENSIONS + detect_language."""

    def test_all_lists_both(self) -> None:
        assert set(languages.__all__) == {"TYPE_EXTENSIONS", "detect_language"}

    def test_re_exported_from_domain_package(self) -> None:
        """`from ac_guard.domain import languages` resolves to this module."""
        from ac_guard import domain

        assert "languages" in domain.__all__
        assert domain.languages is languages
