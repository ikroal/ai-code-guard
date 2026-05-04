"""Contract tests locking the public surface of ``ac_guard.ruleset``.

These tests fail loudly when symbols are added to or removed from the
top-level ``__all__`` without a corresponding update here. They exist to
prevent quiet drift between the module's promised API and its imports.
"""

from __future__ import annotations

import ac_guard.ruleset as rs

_EXPECTED_PUBLIC_API: frozenset[str] = frozenset(
    {
        "RulesetError",
        "RulesetFetchError",
        "RulesetRef",
        "RulesetURLError",
        "RulesetValidationError",
        "clear_cache",
        "fetch_ruleset",
        "get_cache_dir",
        "get_ruleset_dir",
        "list_cached",
        "load_ruleset_config",
        "parse_ruleset_url",
        "read_meta",
    }
)


def test_public_api_exact() -> None:
    """``__all__`` must be exactly the agreed public surface."""
    assert set(rs.__all__) == _EXPECTED_PUBLIC_API


def test_each_public_symbol_is_importable() -> None:
    """Every name in ``__all__`` must resolve on the package."""
    for name in _EXPECTED_PUBLIC_API:
        assert hasattr(rs, name), f"{name} listed in __all__ but not importable"


def test_removed_symbols_not_in_public_api() -> None:
    """Demoted/internal symbols must not appear in the top-level ``__all__``."""
    assert "CACHE_DIR" not in rs.__all__
    assert "validate_ruleset_dir" not in rs.__all__
