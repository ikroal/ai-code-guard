"""Contract tests locking the public surface of ``ac_guard.action_guard``.

These tests fail loudly when symbols are added to or removed from the
top-level ``__all__`` without a corresponding update here. They prevent
quiet drift between the module's promised API and its imports.
"""

from __future__ import annotations

import ac_guard.action_guard as ag

_EXPECTED_PUBLIC_API: frozenset[str] = frozenset(
    {
        "ActionGuardError",
        "Decision",
        "PolicyCorruptError",
        "PolicyDecision",
        "evaluate",
    }
)


def test_public_api_exact() -> None:
    """``__all__`` must be exactly the agreed public surface."""
    assert set(ag.__all__) == _EXPECTED_PUBLIC_API


def test_each_public_symbol_is_importable() -> None:
    """Every name in ``__all__`` must resolve on the package."""
    for name in _EXPECTED_PUBLIC_API:
        assert hasattr(ag, name), f"{name} listed in __all__ but not importable"


def test_demoted_primitives_not_in_public_api() -> None:
    """Internal pipeline primitives must not appear at top level.

    These remain accessible via deep submodule imports for tests, but
    are not part of the package's public contract — only ``evaluate``
    is.
    """
    for name in (
        "classify",
        "load_policy",
        "decide",
        "find_matching_rule",
        "matches",
        "parse_pattern",
        "MatchResult",
        "VALID_SCHEMES",
    ):
        assert name not in ag.__all__, f"{name} should be demoted to internal"


def test_legacy_evaluate_rules_removed() -> None:
    """``evaluate_rules`` was renamed to ``decide``; neither name is public."""
    assert "evaluate_rules" not in ag.__all__
    assert not hasattr(ag, "evaluate_rules")
