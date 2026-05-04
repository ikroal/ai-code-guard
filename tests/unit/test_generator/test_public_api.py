"""Contract tests locking the public surface of ``ac_guard.generator``.

These tests fail loudly when symbols are added to or removed from the
top-level ``__all__`` without a corresponding update here. They prevent
quiet drift between the module's promised API and its imports.
"""

from __future__ import annotations

import ac_guard.generator as gen

_EXPECTED_PUBLIC_API: frozenset[str] = frozenset(
    {
        "ArtifactWriteError",
        "FileSpec",
        "GeneratorError",
        "Installation",
        "create_installation",
        "delete_artifacts",
        "delete_installation",
        "generate_all",
        "installation_path",
        "read_installation",
        "write_artifacts",
        "write_installation",
    }
)


def test_public_api_exact() -> None:
    """``__all__`` must be exactly the agreed public surface."""
    assert set(gen.__all__) == _EXPECTED_PUBLIC_API


def test_each_public_symbol_is_importable() -> None:
    """Every name in ``__all__`` must resolve on the package."""
    for name in _EXPECTED_PUBLIC_API:
        assert hasattr(gen, name), f"{name} listed in __all__ but not importable"


def test_demoted_state_symbols_not_in_public_api() -> None:
    """Old ``state``-named symbols must not appear in the top-level ``__all__``."""
    for name in (
        "STATE_FILE",
        "GeneratedState",
        "read_state",
        "write_state",
        "create_state",
    ):
        assert name not in gen.__all__, f"{name} should be demoted"


def test_demoted_g_primitives_not_in_public_api() -> None:
    """Seven G primitives must be private (deep-import only for tests)."""
    for name in (
        "generate_rule_docs",
        "generate_hook_files",
        "generate_tool_configs",
        "generate_check_scripts",
        "generate_precommit_config",
        "generate_policy_cache",
        "generate_git_hooks",
    ):
        assert name not in gen.__all__, f"{name} should be private"


def test_demoted_exceptions_not_in_public_api() -> None:
    """Dead/misplaced exception classes must not appear at top level."""
    assert "GitDirectoryNotFoundError" not in gen.__all__
    assert "AdapterNotRegisteredError" not in gen.__all__
